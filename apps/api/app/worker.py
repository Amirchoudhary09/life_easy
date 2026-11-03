"""arq worker: `arq app.worker.WorkerSettings`. Runs queued tasks and the cron schedule. Needs REDIS_URL."""

from __future__ import annotations

from typing import Any

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func

from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.tasks.runner import registered_tasks

log = get_logger(__name__)
_tasks = registered_tasks()


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    problems = settings.production_problems()
    if problems:
        raise RuntimeError("Refusing to start in production: " + "; ".join(problems))
    log.info("worker started", tasks=sorted(_tasks))


async def shutdown(ctx: dict[str, Any]) -> None:
    from app.db.session import dispose_engine

    await dispose_engine()


def _cron(name: str, **when: Any) -> Any:
    fn = _tasks[name]
    return cron(fn, name=f"cron_{name}", **when)


class WorkerSettings:
    functions = [func(fn, name=name) for name, fn in _tasks.items()]
    cron_jobs = [
        _cron("ingest_jobs", hour={0, 6, 12, 18}, minute=5),
        _cron("daily_digest", minute=0),  # hourly; each user is picked at their local digest hour
        _cron("follow_ups", hour=4, minute=30),
        _cron("inbox_watch", minute={0, 30}),
        _cron("interview_prep", minute=15),
        _cron("weekly_report", weekday=0, hour=3, minute=0),
        _cron("expire_approvals", minute=45),
        _cron("purge_expired_contacts", hour=2, minute=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379/0")
    max_jobs = 10
    job_timeout = 900
    retry_jobs = True
    max_tries = 3
