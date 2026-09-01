"""Runtime compatibility helpers for optional third-party dependencies."""

from __future__ import annotations

import random as _random
from types import SimpleNamespace


class _Scalar:
    def __init__(self, value):
        self._value = value

    def item(self):
        return self._value


class FallbackNdarray:
    def __init__(self, data):
        self.data = data
        if isinstance(data, list) and data and isinstance(data[0], list):
            self.shape = (len(data), len(data[0]))
        elif isinstance(data, list):
            self.shape = (len(data),)
        else:
            self.shape = ()

    def __getitem__(self, index):
        if isinstance(index, tuple):
            row, col = index
            return self.data[row][col]
        return self.data[index]

    def __setitem__(self, index, value):
        if isinstance(index, tuple):
            row, col = index
            self.data[row][col] = value
        else:
            self.data[index] = value

    def __iter__(self):
        return iter(self.data)

    def __ior__(self, other):
        for row in range(self.shape[0]):
            for col in range(self.shape[1]):
                self.data[row][col] = bool(self.data[row][col] or other[row, col])
        return self


class _FallbackRandom:
    @staticmethod
    def binomial(n, p):
        successes = 0
        for _ in range(n):
            if _random.random() < p:
                successes += 1
        return successes


def _build_numpy_fallback():
    def _build(shape, fill_value):
        if len(shape) == 1:
            return FallbackNdarray([fill_value for _ in range(shape[0])])
        if len(shape) == 2:
            rows, cols = shape
            return FallbackNdarray([[fill_value for _ in range(cols)] for _ in range(rows)])
        if len(shape) == 3:
            depth, rows, cols = shape
            return FallbackNdarray([[[fill_value for _ in range(cols)] for _ in range(rows)] for _ in range(depth)])
        return FallbackNdarray([])

    def _where(arr):
        ys, xs = [], []
        for y in range(arr.shape[0]):
            for x in range(arr.shape[1]):
                if arr[y, x]:
                    ys.append(y)
                    xs.append(x)
        return ys, xs

    return SimpleNamespace(
        float32=float,
        uint8=int,
        ndarray=FallbackNdarray,
        random=_FallbackRandom(),
        zeros=lambda shape, dtype=None: _build(shape, 0 if dtype is not bool else False),
        ones=lambda shape, dtype=None: _build(shape, 1 if dtype not in (bool, False) else True),
        full=lambda shape, fill_value=False, order=None: _build(shape, fill_value),
        array=lambda value, dtype=None: _Scalar(value),
        where=_where,
    )


def _build_requests_fallback():
    class RequestException(Exception):
        pass

    return SimpleNamespace(
        exceptions=SimpleNamespace(RequestException=RequestException),
        post=lambda *args, **kwargs: (_ for _ in ()).throw(
            RequestException("requests fallback stub does not perform network calls")
        ),
    )


def _build_genai_fallback():
    class _Response:
        text = ""

    class _Models:
        def generate_content(self, model, contents, **kwargs):
            return _Response()

    class _Client:
        def __init__(self, *args, **kwargs):
            self.models = _Models()

    return SimpleNamespace(
        Client=_Client,
        configure=lambda **kwargs: None,
    )


try:
    import numpy as np  # type: ignore
except ModuleNotFoundError:
    np = _build_numpy_fallback()

try:
    import requests  # type: ignore
except ModuleNotFoundError:
    requests = _build_requests_fallback()

class _LazyGenAI:
    """Defers importing google.genai until the first attribute access that
    actually needs it, instead of importing it eagerly every time
    runtime_compat (and therefore engine.py, which is imported by
    virtually every test file via `from runtime_compat import genai, np,
    requests`) gets imported. google.genai pulls in a notably heavy
    dependency chain (grpc/protobuf and friends), so on a machine where the
    real package IS installed, this previously added real import cost to
    every single test file's collection even though the overwhelming
    majority of tests never touch an LLM at all.

    Falls back to _build_genai_fallback() exactly as before if the real
    package still isn't importable - behavior for actual genai usage
    (engine.py's GOOGLE_API_KEY-gated genai.configure/genai.Client calls)
    is otherwise unchanged, just resolved lazily instead of at import time.
    Safe specifically because engine.py's own genai.configure call is
    itself gated behind `if GOOGLE_API_KEY and ...` (config.py defaults
    GOOGLE_API_KEY to "" unless a real key is configured) - so in any
    environment without a configured key (every test run, most CI), that
    `and` short-circuits and never triggers resolution at all.
    """

    def __init__(self):
        self._resolved = None

    def _resolve(self):
        if self._resolved is None:
            try:
                from google import genai as _real_genai  # type: ignore
                self._resolved = _real_genai
            except (ModuleNotFoundError, ImportError):
                self._resolved = _build_genai_fallback()
        return self._resolved

    def __getattr__(self, name):
        return getattr(self._resolve(), name)


genai = _LazyGenAI()
