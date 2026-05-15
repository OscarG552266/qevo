# Q-Evo

**Q-Evo** is an adaptive quantum meta-compiler built on top of Qiskit.

It evaluates multiple transpilation strategies for a given quantum circuit, learns from previous outcomes through Bayesian inference, and selects compilation paths that maximize optimization while preserving semantic equivalence.

Unlike static transpilation, Q-Evo continuously refines its strategy selection based on circuit topology, hardware constraints, and prior compilation outcomes.

The framework stores learned strategy profiles and improves decision quality across repeated compilations.

---

## Why Q-Evo

Traditional transpilers apply fixed optimization passes.

Q-Evo treats compilation as a learning problem:
it evaluates, learns and improves strategy selection over time based on circuit structure and backend behavior.

---
## Installation

From the project root directory:

```bash
pip install .
```
---

## Requirements

- Python 3.9+
- numpy>=1.24
- qiskit>=1.0
- qiskit-aer>=0.14
- qiskit-ibm-runtime

---

## How it works

Q-Evo follows a self-improving compilation loop:

1. Analyze circuit structure
2. Extract complexity features
3. Sample candidate strategies via Bayesian Thompson sampling
4. Compile using selected strategy
5. Measure optimization reward
6. Validate semantic equivalence
7. Update internal knowledge
8. Persist learned strategy model

This enables adaptive compilation tailored to both circuit characteristics and backend topology.

---

## Quick Example

```python
import qevo
from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService

service = QiskitRuntimeService(channel="ibm_quantum_platform")
# backend = service.least_busy(simulator=False, operational=True)
backend = service.backend("ibm_fez")

qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)

compiler = qevo.Compiler(backend, state_path=f"./qevo_{backend.name}")

results = compiler.evaluate(qc)
performance = qevo.analyze_performance(results)

print(performance)
```
---
## 📝 Qevo Compiler Cheat-sheet

Use these configurations within the `qevo.Compiler` to customize its behavior:

| Parameter | Description | Default / Example |
| :--- | :--- | :--- |
| `state_path` | Path to the model. Use a shared directory for a global model or unique paths for per-backend models. | `./qevo_model` |
| `learn` | Set to False for read-only mode (disables model updates). | `True` |
| `transpiler_args` | Dictionary for **Qiskit transpiler options** (e.g., `optimization_level`). | `{}` |
| `check_semantic_preservation` | Ensures the compiled circuit is **mathematically equivalent** to the original (this verification can be computationally intensive for large circuits). | `True` |

---

## Core Concepts

### Bayesian Strategy Learning

Each compilation strategy maintains an independent Bayesian linear model.

Q-Evo estimates expected reward under uncertainty and uses Thompson Sampling to balance:

- exploration of unknown strategies
- exploitation of proven strategies

---

## Hardware Awareness

Q-Evo inspects physical backend conditions after transpilation:

- qubit allocation
- coupling graph density
- spatial congestion
- local CX error
- topology pressure

This provides context-aware optimization instead of generic transpilation.

---

## Architecture

The `qevo` framework and its execution examples are structured as follows:

```text
qevo/
├── qevo/                      # Core Library
│   ├── __init__.py            # Package initialization
│   ├── compiler.py          # Adaptive optimization engine
│   ├── analyzer.py          # Circuit structural & complexity analysis
│   ├── models.py            # Bayesian linear model
│   ├── rewards.py           # Reward computation & multi-signal scoring
│   ├── diagnostics.py       # Hardware bottleneck & LLM-compatible reporting
│   └── utils.py             # Feature extraction & helper functions
│
└── examples/                  # Sample Applications & Testing
    ├── load_credentials.py    # IBM Quantum platform authentication helper
    ├── train-qevo.py          # Training loop for continuous strategy learning
    ├── test-qevo.py           # Benchmark script for evaluation verification
    └── qevo-agent.py          # AI Agent integration (QuantumMaster framework)

---

## Semantic Preservation

A candidate circuit is accepted only if semantic consistency is preserved.

Validation is performed in three layers:

### 1. Full unitary verification

Compares operator matrices directly.

### 2. Statevector verification

Used for larger circuits where matrix expansion is expensive.

### 3. DAG subgraph verification

Checks structural consistency over logical circuit regions.

This hybrid validation enables scalable equivalence checks.

---

## Reward System

Compilation quality is scored according to:

### Positive signals

- reduction in 2-qubit gates
- depth reduction
- lower hardware overhead

### Negative signals

- excessive SWAP insertion
- topology expansion
- semantic degradation
- fidelity loss

Semantic failure triggers hard rejection.

---

## Diagnostics

Q-Evo generates interpretable diagnostics for humans and AI agents.

Examples:

- fidelity loss detection
- routing congestion
- excessive hardware expansion
- optimization redundancy

Designed for direct integration with LLM agents.

---

## Features

- adaptive quantum compilation
- Bayesian strategy selection
- self-improving optimization
- backend-aware routing evaluation
- multilevel semantic verification
- reward-guided strategy learning
- persistent knowledge models
- LLM-compatible diagnostics
- feature extraction
- benchmark samples

---

## Strategies

Current compilation modes:

### baseline

Reference compilation.

### routing

Hardware-aware transpilation.

### heavy_opt

Aggressive optimization with controlled approximation.

Each strategy learns independently.

---

## Returned Metrics

Evaluation returns:

- selected strategy
- reward score
- semantic fidelity
- depth expansion
- hardware placement
- topology diagnostics
- Insight report (Useful for an LLM)

---

## Sample Applications

Included examples:

- Training script
- Test example
- AI agent integration (QuantumMaster):
	- Automatic circuit synthesis & correction
	- Compiler explanation assistant
	- Self-Guided learning

AI example requirements:
- Ollama
- langchain
- langchain_ollama
- langgraph
- An LLM: gpt-oss:20b, gpt-oss:120b, deepseek-r1:8b, etc.

---

## Research Scope

Q-Evo is intended for:

- adaptive transpilation research
- backend benchmarking
- quantum compiler experimentation
- semantic verification research
- intelligent compilation systems
- autonomous optimization agents

---

## License

Q-EVO Non-Commercial License v1.0

Free for:

- academic use
- educational use
- research use
- personal use
- non-commercial experimentation

Commercial use requires explicit written authorization.

---

## Author

Oscar García
OscarG552266
