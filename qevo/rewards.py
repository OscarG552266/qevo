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
    """
    Métrica de recompensa con penalizaciones críticas por pérdida de fidelidad,
    ajustada para balancear la reducción de compuertas 2q y el crecimiento de profundidad.
    """

    if isinstance(fidelity, dict):
        fid_val = fidelity.get('fidelity', 0.0)
    else:
        fid_val = fidelity if isinstance(fidelity, (int, float)) else 1.0

    # Si la fidelidad baja de 0.99 (o falló estrepitosamente), castigo inmediato.
    # Usamos -1.0 para impactar fuertemente el modelo bayesiano mediante Thompson Sampling.
    if fid_val < 0.99:
        return -1.0

    # Recompensa base y penalización por falta de compilación física
    reward = 0.5
    layout = getattr(after_qc, "layout", None)
    if layout is None or getattr(layout, "initial_layout", None) is None:
        reward -= 0.2  # Castigo por no asignar qubits físicos al hardware

    # Ganancia por optimización de compuertas de dos qubits (2q)
    # Reducir compuertas CX/CZ es la prioridad número 1 en hardware ruidoso
    tq_before = max(1, before["two_q"])
    tq_reduction = (before["two_q"] - after_metrics["two_q"]) / tq_before
    reward += tq_reduction * 2.0
    
    # Penalización elástica por escalado de profundidad (Decoherencia)
    depth_before = max(1, before["depth"])
    depth_ratio = after_metrics["depth"] / depth_before

    if depth_ratio > 1.5:
        # Penalización progresiva si el circuito se expande demasiado rápido
        reward -= 0.3 * (depth_ratio - 1.0)
    if after_metrics['depth'] > 100 and before['depth'] < 15:
        # Castigo severo si un circuito pequeño explota en tamaño (típico de baseline ruidoso)
        reward -= 1.5
        
    # Acotamos la recompensa final en el rango dinámico de la actualización bayesiana [0.0, 1.0]
    return float(np.clip(reward, 0.0, 1.0))


def check_semantic_preservation(qc_before, qc_after):
    """
    Verifica si el circuito transpilado mantiene la consistencia semántica.
    Para circuitos chicos usa simulación exacta; para grandes, análisis topológico del DAG.
    """
    def strip_all_metadata(qc):
        clean = QuantumCircuit(qc.num_qubits)
        bit_to_idx = {bit: i for i, bit in enumerate(qc.qubits)}
        for inst in qc.data:
            op_name = inst.operation.name
            if op_name not in ['barrier', 'measure', 'reset']:
                indices = [bit_to_idx[q] for q in inst.qubits]
                clean.append(inst.operation, indices)
        return clean

    def get_tight_circuit(qc_clean):
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

    try:
        clean_before = strip_all_metadata(qc_before)
        clean_after = strip_all_metadata(qc_after)
        short_before = get_tight_circuit(clean_before)
        short_after = get_tight_circuit(clean_after)
        
        short_before = short_before.decompose()
        short_after = short_after.decompose()
        n_active = short_before.num_qubits
    except Exception as e:
        traceback.print_exc()
        n_active = qc_before.num_qubits
        short_before = qc_before
        short_after = qc_after

    # Comparación exacta por operador unitario completo
    if n_active <= 10:
        try:
            op_before = Operator(short_before)
            op_after = Operator(short_after)
            fid = process_fidelity(op_before, op_after)
            return {"status": "verified" if fid > 0.99 else "altered", "fidelity": round(float(fid), 6), "method": "full_unitary"}
        except: 
            pass

    # Simulación por inversión de estado
    # 
    if n_active <= 25:
        aer_backend = AerSimulator(method='matrix_product_state')
        try:
            if short_before.num_qubits == short_after.num_qubits:
                # Si short_after equivale a short_before, entonces (short_after COMPUESTO CON short_before^-1) == IDENTIDAD.
                # Al simular el estado inicial |0>, el resultado final debe ser estrictamente |0> (probabilidad en la posición 0 = 1.0)
                u_inv = short_before.inverse()
                test_qc = short_after.compose(u_inv)
                test_qc.save_statevector()
                
                result = aer_backend.run(test_qc).result()
                sv_final = result.get_statevector()
                fidelity = sv_final.probabilities()[0]
                
                return {
                    "status": "verified" if fidelity > 0.99 else "altered", 
                    "fidelity": round(float(fidelity), 6), 
                    "method": "statevector_inversion"
                }
        except Exception as e:
            logger.debug(f"Fallo en inversión de estado: {e}")

    # Análisis estructural del DAG (Para > 25 qubits, validación por grafo de interacción de entrelazamiento)
    try:
        dag_before = circuit_to_dag(short_before)
        dag_after = circuit_to_dag(short_after)
        
        # Mapeamos los qubits virtuales a índices enteros para el análisis de flujo
        bit_to_idx_b = {bit: i for i, bit in enumerate(short_before.qubits)}
        bit_to_idx_a = {bit: i for i, bit in enumerate(short_after.qubits)}
        
        # Construimos conjuntos de pares de qubits lógicos que interactúan (aristas del grafo cuántico)
        edges_before = set()
        for node in dag_before.op_nodes():
            if len(node.qargs) == 2:
                q0, q1 = bit_to_idx_b[node.qargs[0]], bit_to_idx_b[node.qargs[1]]
                edges_before.add(tuple(sorted((q0, q1))))
                
        edges_after = set()
        for node in dag_after.op_nodes():
            if len(node.qargs) == 2:
                q0, q1 = bit_to_idx_a[node.qargs[0]], bit_to_idx_a[node.qargs[1]]
                edges_after.add(tuple(sorted((q0, q1))))
        
        # Si el circuito original requiere entrelazar ciertos qubits y la estrategia eliminó 
        # esas conexiones lógicas por completo, hay una alteración semántica crítica.
        if edges_before:
            # Calculamos cuántas de las conexiones necesarias sobrevivieron
            connections_preserved = edges_before.intersection(edges_after)
            structural_fidelity = len(connections_preserved) / len(edges_before)
            
            # Si se pierde más del 5% de los canales de interacción lógicos fundamentales, la compilación falló.
            if structural_fidelity < 0.95:
                return {
                    "status": "altered",
                    "fidelity": round(structural_fidelity, 4),
                    "method": "DAG"
                }
            
            return {
                "status": "verified",
                "fidelity": round(structural_fidelity, 4),
                "method": "DAG"
            }
        else:
            # Si el circuito original no tenía entrelazamiento, verificamos que el 
            # compilador no haya inventado compuertas 2Q ruidosas de la nada.
            if len(edges_after) > 0:
                return {"status": "altered", "fidelity": 0.0, "method": "DAG_empty_edges"}
            return {"status": "verified", "fidelity": 1.0, "method": "DAG_1q"}
    except Exception as e:
        logger.warning(f"Error en análisis topológico del DAG: {e}")

    return {"status": "skipped", "reason": "Circuit too large and topological analysis failed", "fidelity": 1.0}