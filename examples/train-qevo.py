import qevo
from qiskit import QuantumCircuit
from qiskit.circuit.library import EfficientSU2, QFT
from qiskit.circuit.random import random_clifford_circuit
import os
import numpy as np
import logging
from load_credentials import setup_qiskit_account
logger = logging.getLogger(qevo.__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

service = setup_qiskit_account()
#backend = service.least_busy(simulator=False, operational=True)
backend = service.backend("ibm_fez")

props = backend.properties()
cfg   = backend.configuration()

compiler = qevo.Compiler(backend, learn=False, state_path=f"./qevo_{backend.name}")

# --- Generación de Puzzles de Prueba ---

def generate_topological_puzzle(n_qubits=27, repetitions=2):
    """Crea un circuito con conectividad 'All-to-All', un reto para chips con conectividad limitada."""
    ansatz = EfficientSU2(num_qubits=n_qubits, entanglement='full', reps=repetitions, insert_barriers=True)
    weights = np.random.uniform(0, 2 * np.pi, ansatz.num_parameters)
    circuit = ansatz.assign_parameters(weights)
    
    # Añadimos puertas redundantes para probar si el agente sabe podar código muerto
    redundant_block = QuantumCircuit(n_qubits)
    for i in range(n_qubits):
        redundant_block.h(i)
        redundant_block.h(i)
        redundant_block.x(i)
        redundant_block.x(i)
        
    final_circuit = circuit.compose(redundant_block)
    final_circuit.name = "Entangler_Puzzle"
    return final_circuit

def generate_linear_path_circuit(n_qubits=27):
    """Crea una cadena lineal simple, ideal para verificar un enrutamiento eficiente."""
    qc = QuantumCircuit(n_qubits)
    qc.h(range(n_qubits))
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    for i in range(n_qubits):
        qc.rz(np.random.uniform(0, np.pi), i)
    # Pequeño bloque de identidad real
    qc.x(0)
    qc.x(0)
    qc.name = "Linear_Path"
    return qc

def get_benchmark_circuit(circuit_id, n_qubits=None):
    """
    Fábrica de circuitos de prueba.
    Incluye desde casos simples hasta puzzles topológicos complejos.
    """
    
    # Estructura mínima
    if circuit_id == 1:
        qc = QuantumCircuit(4)
        qc.name="Estructura mínima"
        qc.h(0); qc.cx(0, 1); qc.cx(1, 2)
        return qc

    # Cadena de RY y CX bidireccionales
    elif circuit_id == 2:
        n = n_qubits if n_qubits else 12
        qc = QuantumCircuit(n)
        qc.name="Cadena de RY y CX bidireccionales"
        for i in range(n): qc.ry(np.pi/4, i)
        for i in range(n-1): qc.cx(i, i+1)
        for i in range(n-1): qc.cx(i+1, i)
        return qc

    # Grafo de entrelazamiento denso
    elif circuit_id == 3:
        n = n_qubits if n_qubits else 8
        qc = QuantumCircuit(n)
        qc.name="Grafo de entrelazamiento denso"
        for i in range(n): qc.h(i)
        for i in range(n):
            for j in range(i+1, n): qc.cx(i, j)
        return qc

    # Rotaciones que se anulan en bucle
    elif circuit_id == 4:
        n = n_qubits if n_qubits else 8
        qc = QuantumCircuit(n)
        qc.name="Rotaciones que se anulan en bucle"
        for _ in range(40):
            for q in range(n):
                qc.ry(np.pi/4, q); qc.rz(np.pi/3, q); qc.ry(-np.pi/4, q)
        return qc

    # QFT estándar
    elif circuit_id == 5:
        n = n_qubits if n_qubits else 8
        qc = QFT(num_qubits=n, approximation_degree=0, do_swaps=True)
        qc.name="QFT estándar"
        return qc

    # Circuito de Clifford (Benchmark estándar)
    elif circuit_id == 6:
        n = n_qubits if n_qubits else 8
        qc = random_clifford_circuit(num_qubits=n, num_gates=40)
        qc.name="Circuito de Clifford (Benchmark estándar)"
        return qc

    # Conexiones cruzadas (Mirror)
    elif circuit_id == 7:
        n = n_qubits if n_qubits else 10
        qc = QuantumCircuit(n)
        qc.name="Conexiones cruzadas (Mirror)"
        for i in range(n//2): qc.cx(i, n-1-i)
        for i in range(n//2): qc.cx(n-1-i, i)
        return qc

    # Identidades puras (H-H, CX-CX)
    elif circuit_id == 8:
        qc = QuantumCircuit(6)
        qc.name="Identidades puras (H-H, CX-CX)"
        for _ in range(20):
            qc.h(0); qc.h(0)
            qc.cx(0, 1); qc.cx(0, 1)
            qc.rx(np.pi/3, 2); qc.rx(-np.pi/3, 2)
        return qc

    # Puzzle Topológico: Entrelazamiento Full
    elif circuit_id == 9:
        n = n_qubits if n_qubits else 12
        ansatz = EfficientSU2(num_qubits=n, entanglement='full', reps=1, insert_barriers=True)
        weights = np.random.uniform(0, 2 * np.pi, ansatz.num_parameters)
        circuit = ansatz.assign_parameters(weights)
        
        redundant = QuantumCircuit(n)
        for i in range(n):
            redundant.h(i); redundant.h(i)
            redundant.x(i); redundant.x(i)
        
        qc = circuit.compose(redundant)
        qc.name = "Puzzle Topológico: Entrelazamiento Full"
        return qc

    # Linear Path
    elif circuit_id == 10:
        n = n_qubits if n_qubits else 25
        qc = QuantumCircuit(n)
        qc.h(range(n))
        for i in range(n - 1): qc.cx(i, i + 1)
        for i in range(n): qc.rz(np.random.uniform(0, np.pi), i)
        qc.x(0); qc.x(0)
        qc.name = "Linear Path"
        return qc

    else:
        raise ValueError(f"Circuito {circuit_id} no definido.")

print('Q-Evo: Training tool.\n')

lista_de_circuitos = [get_benchmark_circuit(i) for i in range(1, 11)]
for idx, qc in enumerate(lista_de_circuitos):
    nombre = getattr(qc, 'name', f"Puzzle_{idx+1}")
    print(f"{'='*60}\nENTRENANDO: {nombre} ({qc.num_qubits} qubits)\n{'='*60}")
    results = compiler.evaluate(qc, iterations=20)
    performance = qevo.analyze_performance(results)
    print(f"\n{'ESTRATEGIA':<15} | {'SCORE MEDIO':<15} | {'EFICIENCIA DEPTH'}")
    print("-" * 50)
    for strat, data in performance['strategies'].items():
        avg_score = data['avg_score']
        avg_depth = data['avg_depth']
        std_dev = data['std_dev']
        
        # Marcador de consistencia
        consistency = "✅" if data['consistent'] else "❓"
        
        print(f"{strat:<15} | {avg_score:.4f} ({consistency}) | {avg_depth:.1f} capas")
    print(f"\n🏆 GANADORA TÉCNICA: {performance['best_strategy'].upper()}")

compiler.save_knowledge()
