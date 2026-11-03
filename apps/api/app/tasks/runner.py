"""Background task dispatch.

`enqueue(name, **kwargs)` sends work to the arq worker when REDIS_URL is set.
Without Redis (local dev, tests) the task runs inline in the same process, so
every flow still works end to end on a laptop.

Task functions are registered in app.tasks.registry and executed by app.worker.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

TaskFn = Callable[..., Awaitable[Any]]
_registry: dict[str, TaskFn] = {}
_inline_calls: list[tuple[str, dict[str, Any]]] = []  # tests inspect this
_arq_pool: Any = None


def task(name: str) -> Callable[[TaskFn], TaskFn]:
    def deco(fn: TaskFn) -> TaskFn:
        _registry[name] = fn
        return fn

    return deco


def registered_tasks() -> dict[str, TaskFn]:
    import app.tasks.registry  # noqa: F401  (registers tasks on import)

    return dict(_registry)


async def _get_arq_pool() -> Any:
    global _arq_pool
    if _arq_pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _arq_pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _arq_pool


async def enqueue(name: str, *, _defer_seconds: int | None = None, **kwargs: Any) -> None:
    settings = get_settings()
    if settings.redis_url:
        pool = await _get_arq_pool()
        await pool.enqueue_job(name, _defer_by=_defer_seconds, **kwargs)
        return
    tasks = registered_tasks()
    if name not in tasks:
        raise KeyError(f"unknown task {name!r}")
    _inline_calls.append((name, kwargs))
    if settings.environment == "test" and not _run_inline_in_tests:
        return
    try:
        await tasks[name](None, **kwargs)
    except Exception:  # noqa: BLE001 - inline mode must not break the request
        log.exception("inline task failed", task=name)


_run_inline_in_tests = False


def set_inline_execution_for_tests(enabled: bool) -> None:
    global _run_inline_in_tests
    _run_inline_in_tests = enabled


def inline_calls() -> list[tuple[str, dict[str, Any]]]:
    return list(_inline_calls)


def clear_inline_calls() -> None:
    _inline_calls.clear()


async def close_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None
