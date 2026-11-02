from app.admin import is_allowlisted_admin
def test_admin_allowlist_is_case_insensitive_and_trimmed(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS"," owner@example.com,second@example.com ")
    assert is_allowlisted_admin({"email":"OWNER@example.com"})
    assert is_allowlisted_admin({"email":"second@example.com"})
    assert not is_allowlisted_admin({"email":"other@example.com"})
def test_admin_allowlist_is_empty_by_default(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS",raising=False)
    assert not is_allowlisted_admin({"email":"owner@example.com"})

import asyncio
from app.feature_flags import feature_enabled
class FakeDB:
    def __init__(self,value): self.value=value
    async def fetchval(self,*args): return self.value
def test_feature_flag_uses_database_value():
    assert asyncio.run(feature_enabled(FakeDB(False),"job_search")) is False
    assert asyncio.run(feature_enabled(FakeDB(True),"job_search")) is True
def test_feature_flag_default_when_unset():
    assert asyncio.run(feature_enabled(FakeDB(None),"job_search",True)) is True
