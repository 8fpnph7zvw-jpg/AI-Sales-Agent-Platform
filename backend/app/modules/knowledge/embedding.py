from __future__ import annotations

import hashlib
import math
import re


class EmbeddingService:
    """Deterministic local embedding provider suitable for private deployments.

    It uses signed feature hashing over word and CJK tokens. The interface can be
    replaced by an external embedding model without changing ingestion or retrieval.
    """

    model = "local-feature-hash-v1"

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            vector[value % self.dimensions] += 1.0 if value & 1 else -1.0
        norm = math.sqrt(sum(item * item for item in vector))
        return [item / norm for item in vector] if norm else vector

    @staticmethod
    def similarity(left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=False))
