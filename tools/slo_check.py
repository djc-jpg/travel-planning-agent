"""Evaluate runtime SLO objectives from /metrics snapshot or local JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib import error, request

from app.observability.slo import evaluate_slo_objectives, resolve_slo_objectives

_DEFAULT_OBJECTIVES_PATH = Path("deploy") / "observability" / "slo_objectives.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_metrics_snapshot(base_url: str, token: str = "", timeout: int = 10) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/metrics"
    headers: dict[str, str] = {"Accept": "application/json"}
    if token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    req = request.Request(url=url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
            parsed = json.loads(payload)
            if not isinstance(parsed, dict):
                raise ValueError("metrics response must be JSON object")
            return parsed
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"metrics request failed: status={exc.code} body={body}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate SLO objectives from runtime metrics snapshot")
    parser.add_argument("--base-url", default="", help="Fetch metrics from <base-url>/metrics")
    parser.add_argument("--metrics-json", default="", help="Read metrics snapshot from local JSON file")
    parser.add_argument("--auth-token", default="", help="Optional bearer token for /metrics")
    parser.add_argument("--objectives", default=str(_DEFAULT_OBJECTIVES_PATH))
    parser.add_argument(
        "--profile",
        default="auto",
        choices=["auto", "realtime", "degraded"],
        help="SLO profile selection for profile-based objectives file",
    )
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--output", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    objectives_path = Path(str(args.objectives))
    objectives_config = _load_json(objectives_path)

    metrics_json = str(args.metrics_json).strip()
    base_url = str(args.base_url).strip()
    if metrics_json:
        snapshot = _load_json(Path(metrics_json))
    elif base_url:
        snapshot = _fetch_metrics_snapshot(base_url, token=str(args.auth_token), timeout=int(args.timeout))
    else:
        raise ValueError("either --metrics-json or --base-url must be provided")

    if not isinstance(snapshot, dict):
        raise ValueError("metrics snapshot must be JSON object")

    selected_profile, objectives = resolve_slo_objectives(
        snapshot=snapshot,
        objectives_config=objectives_config,
        profile=str(args.profile),
    )
    report = evaluate_slo_objectives(snapshot, objectives)
    report["profile"] = selected_profile
    report["objectives_file"] = str(objectives_path)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if str(args.output).strip():
        Path(str(args.output)).write_text(rendered + "\n", encoding="utf-8")
    return 0 if bool(report.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
