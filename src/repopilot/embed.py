"""Embedding backends behind one tiny interface (decision #3)."""
from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalised vectors."""


# fastembed pads every text in a batch to the longest one (default batch 256). Chunks vary a lot in length, so
# that wastes most of the compute and memory. Measured on click's chunks, with identical output vectors:
# batch 32: 10.6 chunks/s, 869 MB peak; batch 1: 29.6 chunks/s, 280 MB peak.
EMBED_BATCH = 1


class FastEmbedder:
    """Local ONNX model via fastembed. Loaded lazily so imports stay cheap."""

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model
        self.dim = 384
        self._model = None

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self.model_name)
        vecs = np.array(list(self._model.embed(texts, batch_size=EMBED_BATCH)), dtype=np.float32)
        return vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder for tests and offline use."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in re.findall(r"[a-z0-9]+", t.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
        return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
