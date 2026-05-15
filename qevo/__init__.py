# 1. Exponer las clases y funciones principales
from .compiler import Compiler
from .analyzer import CircuitAnalyzer
from .diagnostics import get_diagnostic, analyze_performance

__name__ = "qevo"
__author__ = "Oscar García"
__version__ = "0.1.0"
__all__ = [
    "Compiler",
    "CircuitAnalyzer",
    "get_diagnostic",
    "analyze_performance",
]
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
