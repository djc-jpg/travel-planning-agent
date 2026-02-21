"""Application context for dependency injection."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from app.application.graph.workflow import compile_graph
from app.infrastructure.cache import poi_cache, route_cache, weather_cache
from app.infrastructure.llm_factory import get_llm
from app.infrastructure.logging import get_logger
from app.infrastructure.session_store import get_session_store
from app.persistence.repository import get_plan_persistence
from app.security.key_manager import get_key_manager


@dataclass
class AppContext:
    session_store: Any
    graph_factory: Callable[[], Any]
    graph_timeout_seconds: int = 120
    engine_version: str = "v2"
    strict_required_fields: bool = False
    llm: Any = None
    cache: dict[str, Any] = field(default_factory=dict)
    key_manager: Any = None
    logger: Any = None
    persistence_repo: Any = None
    _graph: Any = field(default=None, init=False, repr=False)
    _graph_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def get_graph(self) -> Any:
        if self._graph is None:
            with self._graph_lock:
                if self._graph is None:
                    self._graph = self.graph_factory()
        return self._graph


def _is_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def make_app_context() -> AppContext:
    return AppContext(
        session_store=get_session_store(),
        graph_factory=compile_graph,
        graph_timeout_seconds=int(os.getenv("GRAPH_TIMEOUT_SECONDS", "120")),
        engine_version=os.getenv("ENGINE_VERSION", "v2").strip().lower() or "v2",
        strict_required_fields=_is_enabled("STRICT_REQUIRED_FIELDS", default=False),
        llm=get_llm(),
        cache={
            "poi": poi_cache,
            "route": route_cache,
            "weather": weather_cache,
        },
        key_manager=get_key_manager(),
        logger=get_logger(),
        persistence_repo=get_plan_persistence(),
    )
