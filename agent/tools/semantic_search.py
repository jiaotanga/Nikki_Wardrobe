"""使用离线文本向量进行语义检索。"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


PROJECT_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = PROJECT_DIR / "models" / "Qwen3-Embedding-0.6B"
EMBEDDINGS_PATH = PROJECT_DIR / "data" / "derived" / "v1" / "text_embeddings.npz"
SEMANTIC_RESULT_LIMIT = 20
LOGGER = logging.getLogger(__name__)


class SemanticSearch:
    """在满足硬条件的候选部件中进行向量匹配。"""

    def __init__(self) -> None:
        data = np.load(EMBEDDINGS_PATH)
        self.item_ids = data["item_ids"]
        self.embeddings = data["embeddings"]
        self.id_to_index = {
            int(item_id): index for index, item_id in enumerate(self.item_ids)
        }
        self.model = SentenceTransformer(str(MODEL_DIR), device="cuda")

    def search(self, text: str, candidate_ids: list[int]) -> list[int]:
        indices = [
            self.id_to_index[item_id]
            for item_id in candidate_ids
            if item_id in self.id_to_index
        ]
        if not indices:
            return []

        query = (
            "Instruct: Retrieve clothing item descriptions that match the requested "
            f"visual appearance\nQuery: {text}"
        )
        started_at = time.perf_counter()
        LOGGER.info("开始向量检索：%s", text)
        try:
            query_embedding = self.model.encode(
                query,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        finally:
            LOGGER.info(
                "向量编码结束，耗时：%.1f 秒",
                time.perf_counter() - started_at,
            )
        scores = self.embeddings[indices] @ query_embedding
        ranked = np.argsort(scores)[::-1][:SEMANTIC_RESULT_LIMIT]
        return [int(self.item_ids[indices[index]]) for index in ranked]
