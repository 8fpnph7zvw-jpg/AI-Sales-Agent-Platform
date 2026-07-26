from app.modules.knowledge.embedding import EmbeddingService
from app.modules.knowledge.service import RagService


def test_embedding_is_deterministic_and_normalized() -> None:
    service = EmbeddingService(32)
    first = service.embed("stainless steel bottle 500ml")
    second = service.embed("stainless steel bottle 500ml")
    assert first == second
    assert round(sum(value * value for value in first), 6) == 1.0


def test_split_text_uses_overlap() -> None:
    rag = object.__new__(RagService)
    rag.settings = type("Settings", (), {"rag_chunk_size": 10, "rag_chunk_overlap": 2})()
    assert rag.split_text("abcdefghijklmnop") == ["abcdefghij", "ijklmnop"]
