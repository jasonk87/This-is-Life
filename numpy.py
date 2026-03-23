"""Minimal local numpy compatibility shim for the test environment.

This fallback only implements the small slice of NumPy used by the project
tests when the real dependency is unavailable.
"""

from __future__ import annotations

import random as _random


uint8 = int
float32 = float


class _Scalar:
    def __init__(self, value):
        self._value = value

    def item(self):
        return self._value


def _shape_of(data):
    if isinstance(data, list) and data:
        return (len(data),) + _shape_of(data[0])
    if isinstance(data, list):
        return (0,)
    return ()


def _build(shape, fill_value):
    if not shape:
        return fill_value
    return [_build(shape[1:], fill_value) for _ in range(shape[0])]


def _product(shape):
    result = 1
    for dimension in shape:
        result *= dimension
    return result


def _clone(value):
    if isinstance(value, list):
        return [_clone(item) for item in value]
    return value


class ndarray:
    def __init__(self, data=None, *, shape=None, fill_value=0, sparse=False):
        if shape is not None:
            self.shape = tuple(shape)
            self._sparse = sparse
            self._fill_value = fill_value
            self._values = {} if sparse else None
            self.data = None if sparse else _build(self.shape, fill_value)
            return
        self.data = data
        self.shape = _shape_of(data)
        self._sparse = False
        self._fill_value = 0
        self._values = None

    def _resolve_ref(self, index):
        ref = self.data
        for part in index[:-1]:
            ref = ref[part]
        return ref, index[-1]

    def __getitem__(self, index):
        if self._sparse:
            if isinstance(index, tuple):
                if len(index) == len(self.shape):
                    return self._values.get(index, self._fill_value)
                return _SparseView(self, index)
            return _SparseView(self, (index,))
        ref = self.data
        if isinstance(index, tuple):
            for part in index:
                ref = ref[part]
            return ref
        return ref[index]

    def __setitem__(self, index, value):
        if self._sparse:
            key = index if isinstance(index, tuple) else (index,)
            if value == self._fill_value:
                self._values.pop(key, None)
            else:
                self._values[key] = value
            return
        if isinstance(index, tuple):
            ref, last = self._resolve_ref(index)
            ref[last] = value
            return
        self.data[index] = value

    def __iter__(self):
        if self._sparse:
            if len(self.shape) == 1:
                for i in range(self.shape[0]):
                    yield self[i]
                return
            for i in range(self.shape[0]):
                yield self[i]
            return
        return iter(self.data)

    def __ior__(self, other):
        if len(self.shape) != 2:
            raise TypeError("in-place or is only implemented for 2D fallback arrays")
        for row in range(self.shape[0]):
            for col in range(self.shape[1]):
                self[row, col] = bool(self[row, col] or other[row, col])
        return self


class _FallbackRandom:
    @staticmethod
    def binomial(n, p):
        successes = 0
        for _ in range(n):
            if _random.random() < p:
                successes += 1
        return successes


random = _FallbackRandom()


class _SparseView:
    def __init__(self, array: ndarray, prefix: tuple[int, ...]):
        self._array = array
        self._prefix = prefix

    def __getitem__(self, index):
        if isinstance(index, tuple):
            return self._array[self._prefix + index]
        return self._array[self._prefix + (index,)]

    def __setitem__(self, index, value):
        if isinstance(index, tuple):
            self._array[self._prefix + index] = value
        else:
            self._array[self._prefix + (index,)] = value

    def __iter__(self):
        next_dim = self._array.shape[len(self._prefix)]
        for i in range(next_dim):
            yield self[i]


def _make_array(shape, fill_value):
    sparse = _product(shape) > 100_000
    return ndarray(shape=shape, fill_value=fill_value, sparse=sparse)


def zeros(shape, dtype=None):
    fill_value = False if dtype is bool else 0
    return _make_array(shape, fill_value)


def ones(shape, dtype=None):
    fill_value = True if dtype is bool else 1
    return _make_array(shape, fill_value)


def full(shape, fill_value=False, order=None):
    return _make_array(shape, fill_value)


def array(value, dtype=None):
    if isinstance(value, (list, tuple)):
        return ndarray(_clone(list(value)))
    return _Scalar(value)


def where(arr):
    ys, xs = [], []
    for y in range(arr.shape[0]):
        for x in range(arr.shape[1]):
            if arr[y, x]:
                ys.append(y)
                xs.append(x)
    return ys, xs
