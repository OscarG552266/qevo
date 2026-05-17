import qevo
from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_ibm_runtime.exceptions import IBMRuntimeError
from dotenv import load_dotenv
import json
import os
import traceback
import numpy as np
import re
import sys
import logging
logger = logging.getLogger(qevo.__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

from load_credentials import setup_qiskit_account


service = setup_qiskit_account()
backend = service.least_busy(simulator=False, operational=True) 
props = backend.properties()
cfg   = backend.configuration()

compiler = qevo.Compiler(backend, learn=False)

n_qubits = 8
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
print("Original:\n",qc)
results, best_qc = compiler.evaluate(qc, include_best=True)
print("Best:\n",best_qc)
print("Output: \n",re.sub(r'\n\s+(\d+[,\n])',r'\g<1>',json.dumps(results, indent=4)))
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