from .models import BayesianLinear
from .analyzer import CircuitAnalyzer
from .diagnostics import get_diagnostic, get_hardware_status
from .rewards import check_semantic_preservation, compute_reward
from .utils import feature_vector
from qiskit import transpile
from pathlib import Path
import logging
import os
logger = logging.getLogger(__name__.split('.')[0])

class Compiler:
    """
    Un compilador que aprende qué estrategia usar según la topología y complejidad del circuito de entrada.
    """
    def __init__(self, backend, state_path="./qevo_model", learn=True, transpiler_args={}, check_semantic_preservation=True):
        self.models = {}
        self.backend = backend
        self.feature_dim = 9
        self.learn = learn
        self.check_semantic_preservation = check_semantic_preservation
        self.transpiler_args=transpiler_args
        self.strategies = ["baseline", "routing", "heavy_opt"]
        self.state_path = Path(state_path)
        # Directorio donde se guardara lo aprendido.
        os.makedirs(self.state_path, exist_ok=True)
        # Creamos un modelo bayesiano por cada estrategia posible
        for strat in self.strategies:
            model = BayesianLinear(self.feature_dim)
            path = self.state_path / f"{strat}.pkl"
            try:
                if model.load_model(path):
                    logger.info(f"-> Conocimiento cargado para la estrategia: {strat}")
                else:
                    logger.info(f"-> Iniciando conocimiento desde cero para: {strat}")
            except Exception as e:
                logger.warning(f"> Corrupto: {strat}, inicializando nuevo: {e}")
            self.models[strat] = model
        self.analyzer = CircuitAnalyzer()
        
        # Extraemos la información física del hardware
        if hasattr(backend, 'coupling_map'):
            self.coupling_map = backend.coupling_map
        else:
            self.coupling_map = backend.configuration().coupling_map
        self.target = backend.target
    def save_knowledge(self):
        """Guarda el estado de todas las estrategias."""
        for strat, model in self.models.items():
            path = self.state_path / f"{strat}.pkl"
            model.save_model(path)
        logger.info("¡Conocimiento guardado con éxito!")
    def _get_context(self, qc):
        """Prepara el estado actual del circuito antes de elegir una acción."""
        feats = self.analyzer.analyze(qc)
        return feature_vector(feats), feats

    def evaluate(self, qc, shots=10, learn=True):
        results=[]
        for shot in range(shots):
            """Ejecuta el ciclo de decisión, aplicación y aprendizaje."""
            x, before_metrics = self._get_context(qc)
            
            # Thompson Sampling: muestreamos para explorar nuevas estrategias o explotar las conocidas
            samples = {name: model.sample_weights() @ x for name, model in self.models.items()}
            action = max(samples, key=samples.get)

            after_qc = self._apply_strategy(qc, action)
            after_metrics = self.analyzer.analyze(after_qc)
            hw_status = get_hardware_status(action, after_qc, self.backend)
            if self.check_semantic_preservation:
                sem = check_semantic_preservation(qc, after_qc)
                fidelity = sem.get('fidelity', 'N/A')
            else:
                fidelity = 'N/A'
            
            reward = compute_reward(before_metrics, after_qc, after_metrics, fidelity)
            
            # Feedback loop: el modelo aprende si su elección fue buena
            self.models[action].update(x, reward)
            diagnostic = get_diagnostic(action, before_metrics, after_metrics, reward)
            
            results.append({
                "chosen": action, 
                "reward": round(reward, 4), 
                "fidelity": sem,
                "depth_jump": f"{before_metrics['depth']} -> {after_metrics['depth']}",
                "hw_status": hw_status,
                "diagnostic": diagnostic
            })
        if self.learn:
            self.save_knowledge()
        return results



    def _apply_strategy(self, qc, strategy):
        """Aplica la estrategia de transpilación."""
        hw_kwargs = {
            "coupling_map": self.coupling_map,
            "target": self.target,
            "routing_method": "sabre",
            "layout_method": "sabre"
        } | self.transpiler_args


        if strategy == "baseline":
            return transpile(qc, optimization_level=0)
        if strategy == "routing":
            return transpile(qc, optimization_level=2, **hw_kwargs)
        if strategy == "heavy_opt":
            return transpile(qc, optimization_level=3, approximation_degree=0.05, **hw_kwargs)
        return qc
