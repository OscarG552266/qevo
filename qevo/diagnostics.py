import numpy as np

def analyze_performance(outputs):
    """
    Analiza el rendimiento de las estrategias y retorna un objeto detallado
    con las métricas y la ganadora técnica.
    """
    stats = {}
    summary = {
        "strategies": {},
        "best_strategy": None,
        "max_avg_score": -1.0
    }

    # Agrupación de datos
    for res in outputs:
        strat = res['chosen']
        fid_val = res['fidelity'] if isinstance(res['fidelity'], (int, float)) else 1.0
        score = res['reward'] * fid_val 
        
        if strat not in stats:
            stats[strat] = {'scores': [], 'depths': []}
        
        stats[strat]['scores'].append(score)
        
        # Extracción del depth final
        try:
            final_depth = int(res['depth_jump'].split('->')[1])
        except (IndexError, ValueError, AttributeError):
            final_depth = 0 # Fallback
        stats[strat]['depths'].append(final_depth)

    # Cálculo de métricas

    for strat, data in stats.items():
        avg_score = float(np.mean(data['scores']))
        avg_depth = float(np.mean(data['depths']))
        std_dev = float(np.std(data['scores']))
        is_consistent = std_dev < 0.1
        
        # Resumen de esta estrategia
        summary["strategies"][strat] = {
            "avg_score": round(avg_score, 4),
            "avg_depth": round(avg_depth, 2),
            "std_dev": round(std_dev, 4),
            "consistent": is_consistent
        }
        
        # Determinamos la mejor
        if avg_score > summary["max_avg_score"]:
            summary["max_avg_score"] = avg_score
            summary["best_strategy"] = strat
    
    return summary

def get_diagnostic(action, before, after, reward):
    """Genera un reporte legible sobre por qué se tomó la decisión y su impacto."""
    log_depth = max(before['depth'], 1)
    topology_tax = after['depth'] / log_depth
    opt_efficiency = (before['two_q'] - after['two_q']) / max(before['two_q'], 1)
    diagnostic = {
        "strategy_logic": {
            "action": action,
            "reward_tier": "Success" if reward > 0.7 else "Degraded" if reward > 0.1 else "Critical Failure",
            "topology_impact": "High Expansion" if topology_tax > 2.5 else "Stable"
        },
        "gate_physics": {
            "two_q_reduction_pct": f"{round(opt_efficiency * 100, 1)}%",
            "depth_expansion_factor": round(topology_tax, 2)
        },
        "insight": ""
    }
    if reward <= 0:
        diagnostic["insight"] = "Fidelity loss detected. Likely illegal approximations."
    elif topology_tax > 4:
        diagnostic["insight"] = "Kraken routing: connectivity forced excessive SWAP insertion."
    elif opt_efficiency > 0.4:
        diagnostic["insight"] = "High source redundancy: optimization removed many 2-qubit gates."
    return diagnostic

def get_hardware_status(action, after_qc, backend):
    """
    Analiza cómo se asienta el circuito en el hardware real tras la compilación.
    Busca entender si los qubits elegidos están muy dispersos o si están en zonas con mucho ruido.
    """
    config = backend.configuration()
    properties = backend.properties()
    physical_qubits = []

    # Intentamos extraer qué qubits físicos terminó usando el compilador
    layout = getattr(after_qc, "layout", None)
    if layout is not None:
        if hasattr(layout, "initial_layout") and layout.initial_layout is not None:
            try:
                physical_qubits = list(layout.initial_layout.get_physical_bits().keys())
            except Exception:
                pass
        elif hasattr(layout, "get_physical_bits"):
            try:
                physical_qubits = list(layout.get_physical_bits().keys())
            except Exception:
                pass

    physical_qubits = sorted(set(physical_qubits))
    coupling_map = config.coupling_map
    num_qubits = config.n_qubits

    if physical_qubits:
        # Calculamos la dispersión física: ¿están los qubits agrupados o regados por el chip?
        congestion_score = float(np.std(physical_qubits))
        avg_gate_error = 0.0

        if properties:
            errors = []
            # Solo nos interesan los errores de las conexiones que realmente estamos usando
            for q1, q2 in coupling_map:
                if q1 in physical_qubits and q2 in physical_qubits:
                    try:
                        err = properties.gate_error("cx", [q1, q2])
                        if err is not None:
                            errors.append(err)
                    except Exception:
                        continue
            avg_gate_error = float(np.mean(errors)) if errors else 0.0
    else:
        congestion_score = 0.0
        avg_gate_error = 0.0

    # Calculamos el promedio de conexiones por qubit para entender la densidad del grafo
    avg_degree = (2 * len(coupling_map)) / num_qubits if num_qubits > 0 else 0

    return {
        "backend_name": backend.name,
        "n_qubits_total": num_qubits,
        "n_qubits_used": len(physical_qubits),
        "physical_qubits_used": physical_qubits,
        "topology_metrics": {
            "utilization_ratio": round(len(physical_qubits) / num_qubits, 4) if num_qubits else 0,
            "spatial_congestion": round(congestion_score, 2),
            "avg_cx_error_in_zone": round(avg_gate_error, 6),
        },
        "connectivity_graph": {
            "edges": len(coupling_map),
            "avg_degree": round(avg_degree, 2),
        },
    }