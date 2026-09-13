"""为部件文字描述生成文本向量。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "Qwen3-Embedding-0.6B"
DESCRIPTIONS_DIR = ROOT / "data" / "derived" / "v1"
OUTPUT_PATH = DESCRIPTIONS_DIR / "text_embeddings.npz"


def main() -> None:
    paths = sorted(DESCRIPTIONS_DIR.glob("*.json"))
    item_ids = np.array([int(path.stem) for path in paths], dtype=np.int64)
    summaries = [
        json.loads(path.read_text(encoding="utf-8"))["summary_zh"]
        for path in paths
    ]

    model = SentenceTransformer(str(MODEL_DIR), device="cuda")
    embeddings = model.encode(
        summaries,
        batch_size=10,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32, copy=False)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    np.savez(
        OUTPUT_PATH,
        item_ids=item_ids,
        embeddings=embeddings,
    )
    print(f"已生成 {len(item_ids)} 个文本向量：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
