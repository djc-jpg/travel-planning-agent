"""trip-agent CLI entrypoint with single application service."""

from __future__ import annotations

import json
import sys
import uuid

from dotenv import load_dotenv

from app.application.context import make_app_context
from app.application.contracts import TripRequest, TripResult
from app.application.plan_trip import GraphTimeoutError, plan_trip

load_dotenv()


def run_request(message: str, session_id: str | None, ctx) -> TripResult:
    return plan_trip(TripRequest(message=message, session_id=session_id), ctx)


def _format_itinerary(final: dict) -> str:
    lines: list[str] = []
    city = final.get("city", "")
    days = final.get("days", [])
    summary = final.get("summary", "")

    lines.append(f"🗺️ {city}{len(days)}日行程")
    lines.append("=" * 50)

    if summary:
        lines.append(f"\n📝 {summary}\n")

    for day in days:
        day_num = day.get("day_number", "?")
        day_summary = day.get("day_summary", "")
        travel = day.get("total_travel_minutes", 0)

        lines.append(f"\n📅 第{day_num}天" + (f"  |  通勤{travel:.0f}分钟" if travel else ""))
        if day_summary:
            lines.append(f"   {day_summary}")
        lines.append("-" * 50)

        for item in day.get("schedule", []):
            if item.get("is_backup"):
                continue
            poi = item.get("poi", {})
            name = poi.get("name", "?")
            start = item.get("start_time", "")
            end = item.get("end_time", "")
            slot = item.get("time_slot", "")
            cost_str = f"¥{poi.get('cost', 0):.0f}" if poi.get("cost") else "免费"
            travel_min = item.get("travel_minutes", 0)

            time_str = f"{start}-{end}" if start and end else slot
            lines.append(f"  ⏰ {time_str}  📍 {name}  ({cost_str})")

            if travel_min > 0:
                lines.append(f"     🚶 路程约{travel_min:.0f}分钟")

            notes = item.get("notes", "")
            if notes:
                display = notes[:150] + ("..." if len(notes) > 150 else "")
                lines.append(f"     💬 {display}")

        backups = [s for s in day.get("schedule", []) if s.get("is_backup")]
        backups += day.get("backups", [])
        if backups:
            backup_names = [b.get("poi", {}).get("name", "?") for b in backups]
            lines.append(f"  🔁 备选：{'、'.join(backup_names)}")

    total_cost = final.get("total_cost", 0)
    assumptions = final.get("assumptions", [])
    lines.append("\n" + "=" * 50)
    if total_cost:
        lines.append(f"💰 预计总花费：¥{total_cost:.0f}")
    if assumptions:
        lines.append(f"⚠️  注意：{'；'.join(assumptions)}")

    return "\n".join(lines)


def _display_result(result: TripResult) -> str:
    status = result.status.value
    if status == "clarifying":
        print("\n🤔 " + result.message)
        return "clarifying"
    if status == "done":
        final = result.itinerary
        if final:
            print("\n" + _format_itinerary(final))
            print("\n--- 原始 JSON 已保存到 itinerary_output.json ---")
            with open("itinerary_output.json", "w", encoding="utf-8") as f:
                json.dump(final, f, ensure_ascii=False, indent=2)
        return "done"
    print("\n❌ " + (result.message or "未知错误"))
    return "error"


def main():
    print("trip-agent scaffold ok")
    print("=" * 50)
    print("输入旅行需求开始规划，输入 quit 退出\n")

    ctx = make_app_context()

    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        try:
            result = run_request(user_input, None, ctx)
        except GraphTimeoutError as exc:
            print(f"\n❌ 规划超时（{exc.timeout}秒），请简化需求后重试")
            return
        _display_result(result)
        return

    session_id = "cli_session"

    while True:
        try:
            user_input = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见")
            break

        try:
            result = run_request(user_input, session_id, ctx)
        except GraphTimeoutError as exc:
            print(f"\n❌ 对话处理超时（{exc.timeout}秒），请稍后重试")
            continue

        outcome = _display_result(result)
        if outcome == "done":
            print("\n--- 行程已生成。输入新需求开始新规划，或 quit 退出 ---")
            session_id = f"cli_{str(uuid.uuid4())[:8]}"


if __name__ == "__main__":
    main()
