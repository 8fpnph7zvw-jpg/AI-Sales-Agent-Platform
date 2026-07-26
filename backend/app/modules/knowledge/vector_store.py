from __future__ import annotations

import httpx


class ChromaVectorStore:
    """Small Chroma HTTP adapter; MySQL remains the durable source of truth."""

    def __init__(self, base_url: str, collection: str, enabled: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.enabled = enabled

    async def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, str]],
    ) -> None:
        if not self.enabled or not ids:
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/collections",
                json={"name": self.collection, "get_or_create": True},
            )
            response.raise_for_status()
            collection_id = response.json()["id"]
            response = await client.post(
                f"{self.base_url}/api/v1/collections/{collection_id}/upsert",
                json={
                    "ids": ids,
                    "embeddings": embeddings,
                    "documents": documents,
                    "metadatas": metadatas,
                },
            )
            response.raise_for_status()
