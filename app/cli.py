"""trip-agent CLI 入口 — 支持多轮对话"""

from __future__ import annotations

import json
import sys

from dotenv import load_dotenv

from app.application.state_factory import make_initial_state

load_dotenv()  # 自动加载 .env 文件


def _run_graph(state: dict) -> dict:
    import concurrent.futures
    import os
    from app.application.graph.workflow import compile_graph
    timeout = int(os.getenv("GRAPH_TIMEOUT_SECONDS", "120"))
    app = compile_graph()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(app.invoke, state)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return {
                **state,
                "status": "error",
                "messages": state.get("messages", []) + [
                    {"role": "assistant", "content": f"规划超时（{timeout}秒），请简化需求后重试"}
                ],
            }


def _format_itinerary(final: dict) -> str:
    """将 Itinerary JSON 格式化为可读的文本行程单"""
    lines: list[str] = []
    city = final.get("city", "")
    days = final.get("days", [])
    summary = final.get("summary", "")

    lines.append(f"🗺️  {city}{len(days)}日行程")
    lines.append("=" * 50)

    if summary:
        lines.append(f"\n📋 {summary}\n")

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
                lines.append(f"     🚌 路程约{travel_min:.0f}分钟")

            notes = item.get("notes", "")
            if notes:
                # 限制长度，保留前150字符
                display = notes[:150] + ("..." if len(notes) > 150 else "")
                lines.append(f"     💬 {display}")

        # 备选
        backups = [s for s in day.get("schedule", []) if s.get("is_backup")]
        backups += day.get("backups", [])
        if backups:
            backup_names = [b.get("poi", {}).get("name", "?") for b in backups]
            lines.append(f"  🔄 备选：{'、'.join(backup_names)}")

    total_cost = final.get("total_cost", 0)
    assumptions = final.get("assumptions", [])
    lines.append("\n" + "=" * 50)
    if total_cost:
        lines.append(f"💰 预计总花费：¥{total_cost:.0f}")
    if assumptions:
        lines.append(f"⚠️  注意：{'；'.join(assumptions)}")

    return "\n".join(lines)


def _display_result(result: dict) -> str:
    """返回状态标记：done / error / clarifying"""
    status = result.get("status", "unknown")
    if status == "clarifying":
        last_msg = result["messages"][-1] if result.get("messages") else {}
        print("\n🤖 " + last_msg.get("content", ""))
        return "clarifying"
    elif status == "done":
        final = result.get("final_itinerary")
        if final:
            print("\n" + _format_itinerary(final))
            # 同时保存原始 JSON
            print("\n--- 原始 JSON 已保存到 itinerary_output.json ---")
            with open("itinerary_output.json", "w", encoding="utf-8") as f:
                json.dump(final, f, ensure_ascii=False, indent=2)
        return "done"
    elif status == "error":
        last_msg = result["messages"][-1] if result.get("messages") else {}
        print("\n❌ " + last_msg.get("content", "未知错误"))
        return "error"
    else:
        print(f"\n[状态: {status}]")
        return status


def main():
    """支持多轮交互的 CLI。"""
    print("trip-agent scaffold ok")
    print("=" * 50)
    print("输入旅行需求开始规划，输入 quit 退出\n")

    # 单参数模式（单轮）
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        state = make_initial_state()
        state["messages"].append({"role": "user", "content": user_input})
        result = _run_graph(state)
        _display_result(result)
        return

    # 交互模式（多轮）
    from app.infrastructure.session_store import get_session_store
    store = get_session_store()
    session_id = "cli_session"
    state = make_initial_state()

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        state["messages"].append({"role": "user", "content": user_input})

        # 如果之前是 clarifying，走 merge + graph
        if state.get("status") == "clarifying":
            from app.agent.nodes.merge_user_update import merge_user_update_node
            merge_result = merge_user_update_node(state)
            state.update(merge_result)

        result = _run_graph(state)
        state.update(result)
        store.save(session_id, state)

        outcome = _display_result(result)
        if outcome == "done":
            # 可以继续新一轮
            print("\n--- 行程已生成。输入新需求开始新规划，或 quit 退出 ---")
            state = make_initial_state()


if __name__ == "__main__":
    main()
