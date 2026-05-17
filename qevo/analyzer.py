from qiskit.converters import circuit_to_dag, dag_to_circuit
import math
import numpy as np
import networkx as nx

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
    avg_distance = 1.0 + (0.1 * two_q) if two_q > 0 else 1.0 # Si no hay 2q, entonces 1
    entanglement = two_q / max(1, n_active)
    # Medimos qué tan denso es el circuito respecto a su tamaño
    gate_entropy = np.log1p(ops) / np.log(2 + n_active) 

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
    def __init__(self, nx_graph):
        self.nx_graph=nx_graph
    def analyze(self, qc):
        dag = circuit_to_dag(qc)
        # Directed Acyclic Graph: gráfico que conectan tareas o variables sin formar bucles intermitentes.
        ops = qc.count_ops()
        total_ops = sum(ops.values())
        n = qc.num_qubits

        two_q = 0
        distances = []
        # Intentamos obtener el layout físico real si el circuito ya fue transpilado
        layout = getattr(qc, "layout", None)
        initial_layout = getattr(layout, "initial_layout", None) if layout else None

        for node in dag.op_nodes():
            if len(node.qargs) == 2:
                two_q += 1
                if initial_layout:
                    try:
                        # Obtener el índice físico de un objeto Qubit
                        q0_phys = initial_layout.index(node.qargs[0])
                        q1_phys = initial_layout.index(node.qargs[1])
                    except Exception:
                        # Fallback para simuladores o layouts custom
                        try:
                            q0_phys = initial_layout[node.qargs[0]]
                            q1_phys = initial_layout[node.qargs[1]]
                        except Exception:
                            q0_phys = dag.find_bit(node.qargs[0]).index
                            q1_phys = dag.find_bit(node.qargs[1]).index
                else:
                    q0_phys = dag.find_bit(node.qargs[0]).index
                    q1_phys = dag.find_bit(node.qargs[1]).index

                # Usamos NetworkX para calcular la distancia topológica real en el chip
                if self.nx_graph and self.nx_graph.has_node(q0_phys) and self.nx_graph.has_node(q1_phys):
                    try:
                        dist = nx.shortest_path_length(self.nx_graph, source=q0_phys, target=q1_phys)
                        distances.append(dist)
                    except nx.NetworkXNoPath:
                        distances.append(abs(q0_phys - q1_phys)) # Fallback si el grafo está desconectado
                else:
                    distances.append(abs(q0_phys - q1_phys))

        avg_distance = float(np.mean(distances)) if distances else 1.0
        entanglement = two_q / max(n * (n - 1) / 2, 1)

        # Entropía de Shannon
        gate_entropy = 0.0
        if total_ops > 0:
            for v in ops.values():
                p = v / total_ops
                gate_entropy -= p * np.log(p + 1e-12)

        # Presión de hardware: Evaluamos qué tanto stress sufre el chip basado en el grado de conectividad
        # Un circuito con qubits muy distantes en un grafo poco denso eleva la presión de hardware.
        avg_degree = np.mean([d for _, d in self.nx_graph.degree()]) if self.nx_graph and len(self.nx_graph) > 0 else 1.0
        hw_pressure = (avg_distance * n) / (avg_degree * 1.5)

        return {
            "depth": qc.depth(),
            "n_qubits": n,
            "total_ops": total_ops,
            "two_q": two_q,
            "avg_distance": avg_distance,
            "entanglement": entanglement,
            "gate_entropy": gate_entropy,
            "hw_pressure": float(hw_pressure)
        }
