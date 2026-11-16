import json
from datetime import datetime, timedelta, timezone

from production import parity_watch as P

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _w(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return str(path)


def test_unknown_reason_is_never_treated_as_fine():
    assert P.classify("something new happened") == ("unclassified", False)
    assert P.classify("symbol occupied by trend") == ("symbol occupied (modelled)", True)
    assert P.classify("price drift 1.2%")[1] is False


def test_rule_modelled_only_for_some_accounts_is_unknown_elsewhere():
    assert P.classify("daily equity breaker fired", "FirmA-donchian")[1] is True
    cat, known = P.classify("daily equity breaker fired", "FirmB-donchian")
    assert not known and "not modelled for this account" in cat


def test_transient_reject_followed_by_successful_retry_is_not_a_loss(tmp_path):
    rows = [{"event": "decision", "account": "FirmA-trend", "symbol": "XAU", "skipped_reason": "10018 market closed",
             "logged_at": (T0 + timedelta(hours=1)).isoformat()},
            {"event": "decision", "action": "PLACE", "account": "FirmA-trend", "symbol": "XAU",
             "logged_at": (T0 + timedelta(hours=3)).isoformat()},
            {"event": "decision", "account": "FirmA-trend", "symbol": "XAG", "skipped_reason": "10018 market closed",
             "logged_at": (T0 + timedelta(hours=1)).isoformat()}]
    d = P.collect([_w(tmp_path / "j.jsonl", rows)], since=T0)
    bad, _ = P.report(d)
    assert len(bad) == 1 and "market closed: 1" in bad[0], "only the un-retried XAG skip is a loss"


def test_false_occupancy_right_after_a_close_is_flagged(tmp_path):
    rows = [{"event": "outcome", "outcome": "closed", "account": "Exchange-gold", "symbol": "XAG", "attempt_id": "a1",
             "logged_at": (T0 + timedelta(hours=10)).isoformat()},
            {"event": "decision", "account": "Exchange-gold", "symbol": "XAG", "key": "2026-11-01|XAG",
             "skipped_reason": "symbol occupied", "logged_at": (T0 + timedelta(hours=10, minutes=1)).isoformat()}]
    out = P.false_occupancy([_w(tmp_path / "j.jsonl", rows)], since=T0)
    assert len(out) == 1 and "false occupancy" in out[0]
