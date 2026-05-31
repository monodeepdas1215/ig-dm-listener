import importlib
from functools import lru_cache


@lru_cache(maxsize=256)
def import_dotted_path(dotted_path: str) -> any:
    """Import and return a Python object from a dotted path.

    Example: import_dotted_path("agent_framework.graphs.dm.nodes.classify.ClassifyNode")
    → returns the ClassifyNode class
    """
    module_path, _, attr_name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)
