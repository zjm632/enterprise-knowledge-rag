import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.core.config import get_settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int):
        self.dim = dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = tokenize_for_mock_embedding(text)
        if not tokens:
            tokens = [text]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[idx] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


def tokenize_for_mock_embedding(text: str) -> list[str]:
    latin = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    cjk_bigrams = [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return latin + cjk + cjk_bigrams


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_mode.lower() == "openai" and settings.openai_api_key:
        return OpenAIEmbeddingProvider(settings.openai_api_key, settings.openai_base_url, settings.embedding_model)
    return MockEmbeddingProvider(settings.embedding_dim)
