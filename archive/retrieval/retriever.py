"""Hybrid Retriever — 规则 + 向量（向量可选）"""

from __future__ import annotations

from typing import Any, Optional

from app.domain.models import POI
from .index_builder import build_index


def _keyword_score(poi: dict, query: str) -> float:
    """简单关键词匹配评分"""
    score = 0.0
    text = f"{poi.get('name', '')} {poi.get('description', '')} {''.join(poi.get('themes', []))}"
    for word in query:
        if word in text:
            score += 1
    # 按主题匹配
    for theme in poi.get("themes", []):
        if theme in query:
            score += 3
    return score


def retrieve_poi(
    query: str,
    city: str,
    filters: Optional[dict[str, Any]] = None,
    top_k: int = 15,
    faiss_index: Optional[dict] = None,
) -> list[POI]:
    """
    Hybrid 检索：先规则过滤 → 向量排序（可选）→ 多样性去重。
    """
    pois, texts = build_index()

    # 1. 规则过滤：城市
    candidates = [p for p in pois if p["city"] == city]

    # 附加过滤
    if filters:
        if "indoor" in filters and filters["indoor"] is not None:
            candidates = [p for p in candidates if p.get("indoor") == filters["indoor"]]
        if "themes" in filters and filters["themes"]:
            theme_set = set(filters["themes"])
            candidates = [p for p in candidates if set(p.get("themes", [])) & theme_set]

    if not candidates:
        # 降级：只按城市过滤
        candidates = [p for p in pois if p["city"] == city]

    # 2. 排序
    if faiss_index is not None:
        # 向量排序
        try:
            model = faiss_index["model"]
            index = faiss_index["index"]
            full_pois = faiss_index["pois"]

            q_emb = model.encode([query], normalize_embeddings=True)
            scores, indices = index.search(q_emb, min(top_k * 3, len(full_pois)))

            candidate_ids = {p["id"] for p in candidates}
            ranked = []
            for idx in indices[0]:
                if idx < len(full_pois):
                    p = full_pois[int(idx)]
                    if p["id"] in candidate_ids:
                        ranked.append(p)
                        if len(ranked) >= top_k:
                            break
            candidates = ranked if ranked else candidates
        except Exception:
            pass  # 向量搜索失败，回退关键词

    if faiss_index is None:
        # 关键词排序
        candidates.sort(key=lambda p: _keyword_score(p, query), reverse=True)

    # 3. 多样性去重（同主题不超过 3 个）
    theme_count: dict[str, int] = {}
    diversified: list[dict] = []
    for p in candidates:
        dominated = False
        for t in p.get("themes", []):
            if theme_count.get(t, 0) >= 3:
                dominated = True
                break
        if not dominated:
            diversified.append(p)
            for t in p.get("themes", []):
                theme_count[t] = theme_count.get(t, 0) + 1
        if len(diversified) >= top_k:
            break

    return [POI(**p) for p in diversified[:top_k]]
