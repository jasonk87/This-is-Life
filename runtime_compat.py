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
        rows, cols = shape
        return FallbackNdarray([[fill_value for _ in range(cols)] for _ in range(rows)])

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

    class _GenerativeModel:
        def __init__(self, model_name):
            self.model_name = model_name

        def generate_content(self, prompt):
            return _Response()

    return SimpleNamespace(
        GenerativeModel=_GenerativeModel,
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

try:
    import google.generativeai as genai  # type: ignore
except ModuleNotFoundError:
    genai = _build_genai_fallback()
