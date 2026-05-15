import numpy as np
import math
import traceback
import logging
from qiskit_aer import AerSimulator
from qiskit.quantum_info import Statevector, Operator, process_fidelity
from qiskit import QuantumCircuit
from qiskit.converters import circuit_to_dag, dag_to_circuit

logger = logging.getLogger(__name__.split('.')[0])

def compute_reward(before, after_qc, after_metrics, fidelity):
    """Métrica de recompensa con penalizaciones críticas por pérdida de fidelidad."""
    reward = 0.5
    # Penalización por no mapear al hardware (qubits_used == 0)
    layout = getattr(after_qc, "layout", None)
    if layout is None or layout.initial_layout is None:
        reward -= 0.2  # Castigo por no hacer el trabajo de compilación real

    tq_reduction = (before["two_q"] - after_metrics["two_q"]) / max(1, before["two_q"])
    reward += tq_reduction * 2.0
    
    # Penalizamos si el circuito se vuelve demasiado profundo (ruido de decoherencia)
    depth_ratio = after_metrics["depth"] / max(1, before["depth"])
    if depth_ratio > 2.0:
        reward -= 0.5
    if after_metrics['depth'] > 100 and before['depth'] < 10:
        reward -= 2.0
    # Si la fidelidad baja de 0.99, consideramos la compilación un fracaso absoluto ("destrucción" del algoritmo.)
    if fidelity != 'N/A' and fidelity < 0.99:
        return -1.0
    return float(np.clip(reward, 0.0, 1.0))

from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector, Operator, process_fidelity
from qiskit.converters import circuit_to_dag
import traceback
import numpy as np

def check_semantic_preservation(qc_before, qc_after):
    # Limpieza de Layout/Registros, para trabajar con circuitos nuevos "puros" solo con las instrucciones
    def strip_all_metadata(qc):
        # Creamos un circuito nuevo con el mismo número de qubits pero sin registros
        clean = QuantumCircuit(qc.num_qubits)
        bit_to_idx = {bit: i for i, bit in enumerate(qc.qubits)}
        
        # Filtrar y reconstruir
        for inst in qc.data:
            op_name = inst.operation.name
            if op_name not in ['barrier', 'measure', 'reset']:
                # Mapeo manual de qubits a sus índices enteros
                indices = [bit_to_idx[q] for q in inst.qubits]
                clean.append(inst.operation, indices)
        return clean
    # Extraer solo los qubits que realmente tienen puertas
    def get_tight_circuit(qc_clean):
        # Usamos el mismo diccionario de mapeo interno
        bit_to_idx = {bit: i for i, bit in enumerate(qc_clean.qubits)}
        
        active_indices = set()
        for inst in qc_clean.data:
            for q in inst.qubits:
                active_indices.add(bit_to_idx[q])
        
        if not active_indices:
            return QuantumCircuit(1)
            
        sorted_indices = sorted(list(active_indices))
        tight_qc = QuantumCircuit(len(sorted_indices))
        mapping = {old_idx: new_idx for new_idx, old_idx in enumerate(sorted_indices)}
        
        for inst in qc_clean.data:
            new_qubits = [mapping[bit_to_idx[q]] for q in inst.qubits]
            tight_qc.append(inst.operation, new_qubits)
        return tight_qc

    # Intentamos reducir ambos circuitos al mínimo espacio posible
    try:
        clean_before = strip_all_metadata(qc_before)
        clean_after = strip_all_metadata(qc_after)
        short_before = get_tight_circuit(clean_before)
        short_after = get_tight_circuit(clean_after)
        # Para EfficientSU2 y similares
        short_before = short_before.decompose().decompose()
        short_after = short_after.decompose().decompose()
        n_active = short_before.num_qubits
    except Exception as e:
        traceback.print_exc()
        n_active = qc_before.num_qubits
        short_before = qc_before
        short_after = qc_after
    # Unitario (Solo si es realmente pequeño)
    if n_active <= 10:
        try:
            op_before = Operator(short_before)
            op_after = Operator(short_after)
            fid = process_fidelity(op_before, op_after)
            return {"status": "verified" if fid > 0.99 else "altered", "fidelity": round(float(fid), 6), "method": "full_unitary"}
        except: pass
    # DAG Sampling > 27 qubits mucho mas rápido y eficiente.
    try:
        dag_before = circuit_to_dag(short_before)
        dag_after = circuit_to_dag(short_after)
        before_2q = [n for n in dag_before.op_nodes() if len(n.qargs) == 2]
        after_2q = [n for n in dag_after.op_nodes() if len(n.qargs) == 2]
        if not before_2q: # Fallback a 1-qubit si no hay 2-qubit
            before_2q = [n for n in dag_before.op_nodes() if n.op.name not in ['barrier', 'measure']]
            after_2q = [n for n in dag_after.op_nodes() if n.op.name not in ['barrier', 'measure']]
        if len(before_2q) == len(after_2q) and len(before_2q) > 0:
            sample_size = min(len(before_2q), len(after_2q), 5)
            fidelities = []
            for i in range(sample_size):
                # Extraemos la matriz de la puerto y no del circuito completo.
                op_b = Operator(before_2q[i].op)
                op_a = Operator(after_2q[i].op)
                if op_b.num_qubits == op_a.num_qubits:
                    fidelities.append(process_fidelity(op_b, op_a))
            if fidelities:
                avg_fid = sum(fidelities) / len(fidelities)
                if avg_fid > 0.999:
                    return {"status": "verified", "fidelity": round(avg_fid, 4), "method": "DAG_block_sampling"}
    except Exception as e:
        traceback.print_exc()
    # Inversión por Statevector (Hasta ~24 qubits), muy lento
    if n_active <= 27:
        logger.warning(f"> Verificando con inversión por Statevector, puede tardar.")
        aer_backend = AerSimulator(method='matrix_product_state')
        try:
            if short_before.num_qubits == short_after.num_qubits:
                # Invertimos y componemos
                u_inv = short_before.inverse()
                test_qc = short_after.compose(u_inv)
                test_qc.save_statevector()
                # Ejecutamos la simulación
                result = aer_backend.run(test_qc).result()
                # Obtenemos el StateVector
                sv_final = result.get_statevector()
                fidelity = sv_final.probabilities()[0]
                return {"status": "verified" if fidelity > 0.95 else "altered", "fidelity": round(float(fidelity), 6), "method": "statevector_inversion"}
        except Exception as e:
            pass
    return {"status": "skipped", "reason": "All methods failed"}
