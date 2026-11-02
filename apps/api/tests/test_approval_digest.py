from app.approvals import digest
def test_digest_is_stable_for_same_payload():
    payload={"channel":"gmail","recipient":"recruiter@example.com","message":"Hello","subject":"Role"}
    assert digest(payload)==digest(dict(payload))
def test_digest_changes_when_destination_or_body_changes():
    payload={"channel":"gmail","recipient":"recruiter@example.com","message":"Hello","subject":"Role"}
    changed={**payload,"message":"Hello again"}
    assert digest(payload)!=digest(changed)
