import numpy as np

def feature_vector(f):
    """Convierte el diccionario de métricas en un vector numérico escalado."""
    return np.array([
        np.log1p(f["depth"]),
        np.log1p(f["total_ops"]),
        np.log1p(f["two_q"]),
        f["entanglement"],
        f["avg_distance"],
        f["gate_entropy"],
        f.get("hw_pressure", 0.0),
        np.log1p(f["n_qubits"]),
        1.0 # Sesgo (bias)
    ], dtype=np.float32)