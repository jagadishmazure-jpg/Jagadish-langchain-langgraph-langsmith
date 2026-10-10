"""Lexical hashing embeddings: deterministic, offline, and good enough to make retrieval meaningful.

Each text becomes a bag of lower-cased word stems and word bigrams hashed into ``dim`` buckets and
L2-normalised, so cosine similarity tracks shared vocabulary. It is a stand-in for a real embedding
model (Azure OpenAI ``text-embedding-3-large`` and others plug in through ``init_embeddings``): it has
no notion of synonyms, which the retrieval scenario reports honestly.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re

from langchain_core.embeddings import Embeddings

STOP = set("a an the of to and or for in on at is are was be by with from this that it as i my me we our you your do does can".split())


def stems(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


class HashingEmbeddings(Embeddings):
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        toks = stems(text)
        feats = toks + [f"{a}_{b}" for a, b in itertools.pairwise(toks)]
        for f in feats:
            h = int(hashlib.md5(f.encode(), usedforsecurity=False).hexdigest(), 16)
            v[h % self.dim] += -1.0 if (h >> 20) & 1 else 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)
