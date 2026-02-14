"""FailGracefully 节点 — 结构化错误输出，带友好提示"""

from __future__ import annotations

from typing import Any

from app.domain.models import ErrorResponse

# 错误码 → 用户友好提示
_ERROR_TIPS: dict[str, str] = {
    "NO_CANDIDATES": "没有找到该城市的景点数据。请确认城市名称是否正确，或尝试其他城市。",
    "PLANNER_ERROR": "行程规划过程出现异常，请稍后重试。",
    "UNKNOWN": "遇到了意料之外的问题，请稍后重试或换个说法描述需求。",
    "VALIDATION_FAILED": "行程验证未通过，可能存在时间冲突或预算超限。",
}


def fail_gracefully_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    FailGracefully 节点：异常时返回结构化错误 + 友好提示。
    """
    error_msg = state.get("error_message", "未知错误")
    error_code = state.get("error_code", "UNKNOWN")

    # 从 validation_issues 中获取更多上下文
    issues = state.get("validation_issues", [])
    details = state.get("error_details", [])
    for issue in issues:
        if isinstance(issue, dict):
            msg = issue.get("message", "")
            if msg and msg not in details:
                details.append(msg)

    # 获取友好提示
    tip = _ERROR_TIPS.get(error_code, _ERROR_TIPS["UNKNOWN"])

    error = ErrorResponse(
        error=True,
        code=error_code,
        message=str(error_msg) if error_msg != "未知错误" else tip,
        details=details,
    )

    messages = list(state.get("messages", []))
    messages.append({
        "role": "assistant",
        "content": f"抱歉，{tip}\n\n"
                   f"💡 你可以试试：\n"
                   f"  • '我想去北京玩3天，喜欢历史和美食'\n"
                   f"  • '杭州2日游，预算每天500元'\n"
                   f"  • '成都5天亲子游，轻松节奏'",
    })

    return {
        "final_itinerary": None,
        "status": "error",
        "messages": messages,
        "error_response": error.model_dump(mode="json"),
    }
