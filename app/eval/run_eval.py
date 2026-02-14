"""评测运行器 — 逐条评分 + 回归检测 + 报告持久化"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.application.graph.workflow import compile_graph
from app.application.state_factory import make_initial_state
from app.domain.models import Itinerary

_EVAL_OUTPUT_DIR = Path(__file__).parent / "reports"


def _load_cases() -> list[dict]:
    p = Path(__file__).parent / "cases.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _make_state(message: str) -> dict[str, Any]:
    state = make_initial_state()
    state["messages"] = [{"role": "user", "content": message}]
    return state


def _score_case(case: dict, result: dict) -> dict[str, Any]:
    """对单条 case 评分，返回分项得分"""
    expect = case.get("expect", {})
    scores: dict[str, float] = {}
    details: list[str] = []

    status = result.get("status", "unknown")

    # 如果期望 clarifying
    if expect.get("status") == "clarifying":
        scores["status_match"] = 1.0 if status == "clarifying" else 0.0
        return {"scores": scores, "details": details, "total": sum(scores.values()) / max(len(scores), 1)}

    # 1. Schema 合法性
    final = result.get("final_itinerary")
    if final:
        try:
            it = Itinerary.model_validate(final)
            scores["schema_valid"] = 1.0
        except Exception as e:
            scores["schema_valid"] = 0.0
            details.append(f"Schema 校验失败: {e}")
            it = None
    else:
        scores["schema_valid"] = 0.0
        it = None
        if status == "clarifying":
            details.append("进入追问状态，未生成行程")

    if it is None:
        scores.setdefault("days_match", 0.0)
        scores.setdefault("budget_ok", 0.5)
        scores.setdefault("theme_hit", 0.0)
        scores.setdefault("travel_time", 0.5)
        total = sum(scores.values()) / max(len(scores), 1)
        return {"scores": scores, "details": details, "total": total}

    # 2. 天数匹配
    expected_days = expect.get("days")
    if expected_days:
        scores["days_match"] = 1.0 if len(it.days) == expected_days else 0.0
    else:
        scores["days_match"] = 1.0

    # 3. 预算
    budget_limit = expect.get("budget_per_day")
    if budget_limit and it.total_cost > 0:
        total_budget = budget_limit * len(it.days)
        if it.total_cost <= total_budget:
            scores["budget_ok"] = 1.0
        elif it.total_cost <= total_budget * 1.2:
            scores["budget_ok"] = 0.5
        else:
            scores["budget_ok"] = 0.0
            details.append(f"超预算: {it.total_cost:.0f} > {total_budget:.0f}")
    else:
        scores["budget_ok"] = 1.0  # 无预算约束

    # 4. 主题命中率
    expected_themes = set(expect.get("themes", []))
    if expected_themes:
        all_themes: set[str] = set()
        for day in it.days:
            for item in day.schedule:
                all_themes.update(item.poi.themes)
        hit = len(expected_themes & all_themes)
        scores["theme_hit"] = hit / len(expected_themes)
    else:
        scores["theme_hit"] = 1.0

    # 5. 日均出行时间（越短越好，120 分钟以下满分）
    if it.days:
        avg_travel = sum(d.total_travel_minutes for d in it.days) / len(it.days)
        if avg_travel <= 120:
            scores["travel_time"] = 1.0
        elif avg_travel <= 180:
            scores["travel_time"] = 0.5
        else:
            scores["travel_time"] = 0.0
            details.append(f"日均出行时间过长: {avg_travel:.0f}分钟")
    else:
        scores["travel_time"] = 0.0

    total = sum(scores.values()) / max(len(scores), 1)
    return {"scores": scores, "details": details, "total": total}


def run_eval():
    """运行所有评测 case 并输出报告"""
    cases = _load_cases()
    graph = compile_graph()

    print("=" * 60)
    print("trip-agent 评测报告")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []
    total_score = 0.0

    for case in cases:
        case_id = case["id"]
        name = case["name"]

        t0 = time.time()
        try:
            state = _make_state(case["input"])
            result = graph.invoke(state)
            elapsed = time.time() - t0

            score_info = _score_case(case, result)
        except Exception as e:
            elapsed = time.time() - t0
            score_info = {
                "scores": {"error": 0.0},
                "details": [f"异常: {e}"],
                "total": 0.0,
            }

        total_score += score_info["total"]
        results.append({
            "case_id": case_id,
            "name": name,
            "elapsed": round(elapsed, 2),
            **score_info,
        })

        status_icon = "✓" if score_info["total"] >= 0.8 else ("△" if score_info["total"] >= 0.5 else "✗")
        print(f"\n{status_icon} [{case_id}] {name}")
        print(f"  分数: {score_info['total']:.2f} | 耗时: {elapsed:.2f}s")
        for k, v in score_info["scores"].items():
            print(f"    {k}: {v:.2f}")
        for d in score_info.get("details", []):
            print(f"    ⚠ {d}")

    avg = total_score / len(cases) if cases else 0
    print("\n" + "=" * 60)
    print(f"总评: {avg:.2f} ({len(cases)} 条 case)")
    passed = sum(1 for r in results if r["total"] >= 0.8)
    print(f"通过率: {passed}/{len(cases)} ({passed / len(cases) * 100:.0f}%)")
    print("=" * 60)

    # ── 回归检测 ──────────────────────────────────────
    regression = _check_regression(results)
    if regression:
        print("\n⚠️  回归检测:")
        for r in regression:
            print(f"  {r}")

    # ── 保存报告 ──────────────────────────────────────
    report = {
        "timestamp": datetime.now().isoformat(),
        "average_score": round(avg, 4),
        "pass_rate": round(passed / len(cases), 4) if cases else 0,
        "total_cases": len(cases),
        "passed": passed,
        "results": results,
        "regressions": regression,
    }
    _save_report(report)

    return results


def _check_regression(results: list[dict]) -> list[str]:
    """与最近一次报告对比，检测回归（分数下降超过 0.1 的 case）"""
    last_report = _load_last_report()
    if last_report is None:
        return []

    last_scores = {}
    for r in last_report.get("results", []):
        last_scores[r["case_id"]] = r.get("total", 0)

    regressions = []
    for r in results:
        cid = r["case_id"]
        if cid in last_scores:
            delta = r.get("total", 0) - last_scores[cid]
            if delta < -0.1:
                regressions.append(
                    f"[{cid}] {r.get('name', '')} 分数下降: "
                    f"{last_scores[cid]:.2f} → {r.get('total', 0):.2f} (Δ={delta:+.2f})"
                )
    return regressions


def _save_report(report: dict) -> None:
    """将评测报告保存到 eval/reports/ 目录"""
    _EVAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = _EVAL_OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📄 报告已保存: {filepath}")

    # 同时维护一个 latest.json 方便回归对比
    latest = _EVAL_OUTPUT_DIR / "latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)


def _load_last_report() -> dict | None:
    """加载最近一次评测报告"""
    latest = _EVAL_OUTPUT_DIR / "latest.json"
    if not latest.exists():
        return None
    try:
        with open(latest, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


if __name__ == "__main__":
    run_eval()
