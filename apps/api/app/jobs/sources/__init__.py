"""Job-source adapters. Each one talks to a permitted public API and returns JobPosting records.

Board feeds (one company each): greenhouse, lever, ashby, workable, smartrecruiters.
Search API (many companies): adzuna.
"""

from __future__ import annotations

from app.jobs.sources import adzuna, ashby, greenhouse, lever, smartrecruiters, workable
from app.jobs.sources.base import BoardSource, JobPosting, SearchSource

BOARD_SOURCES: dict[str, BoardSource] = {
    "greenhouse": greenhouse.GreenhouseSource(),
    "lever": lever.LeverSource(),
    "ashby": ashby.AshbySource(),
    "workable": workable.WorkableSource(),
    "smartrecruiters": smartrecruiters.SmartRecruitersSource(),
}

SEARCH_SOURCES: dict[str, SearchSource] = {
    "adzuna": adzuna.AdzunaSource(),
}

__all__ = ["BOARD_SOURCES", "SEARCH_SOURCES", "JobPosting"]
