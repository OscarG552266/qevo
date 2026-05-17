from .models import BayesianLinear
from .analyzer import CircuitAnalyzer
from .diagnostics import get_diagnostic, get_hardware_status
from .rewards import check_semantic_preservation, compute_reward
from .utils import feature_vector
from qiskit import transpile
from pathlib import Path
import logging
import numpy as np
import networkx as nx
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
        
        # Extraemos la información física del hardware
        if hasattr(backend, 'coupling_map'):
            self.coupling_map = backend.coupling_map
        elif hasattr(backend, 'configuration'):
            self.coupling_map = backend.configuration().coupling_map
        else:
            self.coupling_map = None
        self.nx_graph = nx.Graph()
        if self.coupling_map:
            self.nx_graph.add_edges_from(self.coupling_map.get_edges())
        else:
            # Si es un simulador ideal sin restricciones de conectividad, creamos un grafo vacío o nulo
            pass
        self.analyzer = CircuitAnalyzer(self.nx_graph)
        self.target = getattr(backend, 'target', None)
    def save_knowledge(self, strats=None):
        """Guarda el estado de todas las estrategias."""
        if strats is None:
            strats=self.models.keys()
        for strat in strats:
            path = self.state_path / f"{strat}.pkl"
            self.models[strat].save_model(path)
        logger.info("¡Conocimiento guardado con éxito!")
    def _get_context(self, qc):
        """Prepara el estado actual del circuito antes de elegir una acción."""
        feats = self.analyzer.analyze(qc)
        return feature_vector(feats), feats

    def evaluate(self, qc, iterations=10, include_best=False, learn_threshold_ratio=0.85):
        """Ejecuta el ciclo de decisión, aplicación y aprendizaje."""
        results = []
        best_qc = None
        best_action = None
        max_score = -float('inf')
        min_depth = float('inf')
        
        # Estructuras para promediar el rendimiento real en el contexto x
        history_per_strategy = {}
        
        hw_kwargs_base = {
            "coupling_map": self.coupling_map,
            "target": self.target
        }
        if hw_kwargs_base["target"] is None:
            del hw_kwargs_base["target"]
        hw_kwargs_base = hw_kwargs_base | self.transpiler_args
        
        qc_canonical = transpile(qc, optimization_level=0, **hw_kwargs_base)
        x, before_metrics = self._get_context(qc_canonical)
        
        for iteration in range(iterations):
            # Thompson Sampling
            samples = {name: model.sample_weights() @ x for name, model in self.models.items()}
            action = max(samples, key=samples.get)

            after_qc = self._apply_strategy(qc_canonical, action)
            after_metrics = self.analyzer.analyze(after_qc)
            hw_status = get_hardware_status(action, after_qc, self.backend)
            
            sem = {"status": "skipped", "reason": "Check semantic preservation disabled", "fidelity": 1.0}
            if self.check_meaningful_preservation if hasattr(self, 'check_meaningful_preservation') else self.check_semantic_preservation:
                sem = check_semantic_preservation(qc_canonical, after_qc)
                fidelity = sem.get('fidelity', 'N/A')
            else:
                fidelity = 'N/A'
            
            reward = compute_reward(before_metrics, after_qc, after_metrics, fidelity)
            score = reward * (fidelity if isinstance(fidelity, (int, float)) else 1.0)
            
            # Guardamos todo el historial para un entrenamiento bayesiano
            if action not in history_per_strategy:
                history_per_strategy[action] = {'scores': [], 'rewards': []}
            history_per_strategy[action]['scores'].append(score)
            history_per_strategy[action]['rewards'].append(reward)
            
            # Desempate:
            is_better_score = score > max_score
            is_tie_but_shorter = (np.isclose(score, max_score) and after_metrics['depth'] < min_depth)
            
            if is_better_score or is_tie_but_shorter:
                max_score = score
                min_depth = after_metrics['depth']
                best_qc = after_qc
                best_action = action
                
            diagnostic = get_diagnostic(action, before_metrics, after_metrics, reward)
            
            results.append({
                "chosen": action, 
                "reward": round(reward, 4), 
                "fidelity": sem,
                "depth_jump": f"{before_metrics['depth']} -> {after_metrics['depth']}",
                "hw_status": hw_status,
                "diagnostic": diagnostic
            })
            
        approved_strategies = []
        if max_score > -float('inf'):
            min_acceptable_score = max_score * learn_threshold_ratio if max_score > 0 else max_score / learn_threshold_ratio
            
            # Filtramos basándonos en el rendimiento esperado (medio) de la estrategia
            for strat, data in history_per_strategy.items():
                avg_score = np.mean(data['scores'])
                avg_reward = np.mean(data['rewards'])
                
                excellent = (np.isclose(avg_score, max_score)) or (avg_score >= min_acceptable_score)
                poor = (avg_reward <= 0.1)
                
                if excellent or poor:
                    approved_strategies.append(strat)
                    # El modelo se actualiza con el reward promedio representativo del contexto x
                    self.models[strat].update(x, avg_reward)
                    
        if approved_strategies and self.learn:
            self.save_knowledge(approved_strategies)            
        if include_best:
            return results, best_qc
        return results



    def _apply_strategy(self, qc, strategy):
        """Aplica la estrategia de transpilación."""
        hw_kwargs = {
            "coupling_map": self.coupling_map,
            "target": self.target,
            "routing_method": "sabre",
            "layout_method": "sabre"
        }
        if hw_kwargs["target"] is None:
            del hw_kwargs["target"]
        hw_kwargs = hw_kwargs | self.transpiler_args

        if strategy == "baseline":
            return transpile(qc, optimization_level=0, **hw_kwargs)
        if strategy == "routing":
            return transpile(qc, optimization_level=2, **hw_kwargs)
        if strategy == "heavy_opt":
            return transpile(qc, optimization_level=3, approximation_degree=0.05, **hw_kwargs)
        return qc