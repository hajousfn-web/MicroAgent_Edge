"""Pluggable device and runtime adapters."""
from adapters.base_adapter import BaseEnvironmentAdapter
from adapters.embedded_c import EmbeddedCAdapter
from adapters.python_edge import PythonEdgeAdapter
__all__ = ['BaseEnvironmentAdapter', 'EmbeddedCAdapter', 'PythonEdgeAdapter']
