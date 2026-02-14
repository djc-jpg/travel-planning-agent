"""向量索引构建器 — 为 POI 建立本地向量索引"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def _poi_to_text(poi: dict) -> str:
    """将 POI 转为文本描述用于向量化"""
    themes = "、".join(poi.get("themes", []))
    indoor = "室内" if poi.get("indoor") else "室外"
    return (
        f"{poi['name']}（{poi['city']}）：{poi.get('description', '')}。"
        f"主题：{themes}。{indoor}景点，游玩约{poi.get('duration_hours', 1.5)}小时，"
        f"费用约{poi.get('cost', 0)}元。"
    )


def build_index(data_path: Optional[str] = None) -> tuple[list[dict], list[str]]:
    """
    构建索引数据。

    返回: (poi_list, text_list) 用于后续向量化。
    若 FAISS/Chroma 不可用，退化为纯文本搜索。
    """
    if data_path is None:
        data_path = str(Path(__file__).resolve().parents[1] / "data" / "poi_v1.json")

    with open(data_path, encoding="utf-8") as f:
        pois = json.load(f)

    texts = [_poi_to_text(p) for p in pois]
    return pois, texts


def build_faiss_index(data_path: Optional[str] = None):
    """
    尝试构建 FAISS 索引。
    需要安装 faiss-cpu 和 sentence-transformers。
    若不可用则返回 None。
    """
    try:
        import faiss  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError:
        return None

    pois, texts = build_index(data_path)
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    embeddings = model.encode(texts, normalize_embeddings=True)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    return {"index": index, "model": model, "pois": pois, "texts": texts}
