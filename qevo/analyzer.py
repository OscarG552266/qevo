from qiskit.converters import circuit_to_dag, dag_to_circuit
import math
import numpy as np

# Extracción de caracteristicas:
# Entrelazamiento y 2q.
# Profundidad y Entropia
# Presión de hardware
# Conectividad.

def extract_features(qc):
    """
    Resume la complejidad del circuito en un conjunto de métricas numéricas.
    """
    active_qubits = set()
    for inst in qc.data:
        for qarg in inst.qubits:
            active_qubits.add(qarg)
    
    n_active = len(active_qubits) if len(active_qubits) > 0 else qc.num_qubits
    depth = qc.depth()
    ops = len(qc.data)
    two_q = sum(1 for inst in qc.data if len(inst.qubits) == 2)

    # Estimación del costo de conectividad basado en puertas de dos qubits (2q).
    avg_distance = 1.0 + (0.1 * two_q)
    entanglement = two_q / max(1, n_active)
    # Medimos qué tan denso es el circuito respecto a su tamaño
    gate_entropy = math.log(ops + 1) / math.log(2 + n_active)

    return {
        "depth": depth,
        "n_qubits": n_active,
        "total_ops": ops,
        "two_q": two_q,
        "avg_distance": avg_distance,
        "entanglement": entanglement,
        "gate_entropy": gate_entropy
    }


class CircuitAnalyzer:
    """
    Herramienta interna para diseccionar la estructura de los nodos del circuito (DAG).
    """
    def analyze(self, qc):
        dag = circuit_to_dag(qc)
        # Directed Acyclic Graph: gráfico que conectan tareas o variables sin formar bucles intermitentes.
        ops = qc.count_ops()
        total_ops = sum(ops.values())
        n = qc.num_qubits

        two_q = 0
        distances = []
        for node in dag.op_nodes():
            if len(node.qargs) == 2:
                q0 = dag.find_bit(node.qargs[0]).index
                q1 = dag.find_bit(node.qargs[1]).index
                two_q += 1
                distances.append(abs(q0 - q1))

        avg_distance = np.mean(distances) if distances else 0.0
        entanglement = two_q / max(n * (n - 1) / 2, 1)

        # Calculamos la entropía de las puertas para ver la diversidad de instrucciones
        gate_entropy = 0.0
        for v in ops.values():
            p = v / max(total_ops, 1)
            gate_entropy -= p * np.log(p + 1e-12)

        return {
            "depth": qc.depth(),
            "n_qubits": n,
            "total_ops": total_ops,
            "two_q": two_q,
            "avg_distance": avg_distance,
            "entanglement": entanglement,
            "gate_entropy": gate_entropy,
            # Normalizamos la presión del hardware para circuitos pequeños
            "hw_pressure": n / (qc.num_qubits * 1.5)
        }
