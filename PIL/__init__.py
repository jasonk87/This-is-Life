from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys


def _load_real_pillow():
    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    search_paths = []
    for path in sys.path:
        normalized = os.path.abspath(path or os.getcwd())
        if normalized == package_root:
            continue
        search_paths.append(path)

    spec = importlib.machinery.PathFinder.find_spec(__name__, search_paths)
    if spec is None or spec.loader is None or spec.origin == __file__:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)
    return module


_REAL_PILLOW = _load_real_pillow()

if _REAL_PILLOW is not None:
    globals().update(_REAL_PILLOW.__dict__)
else:
    from . import Image

    open = Image.open

    __all__ = ["Image", "open"]
