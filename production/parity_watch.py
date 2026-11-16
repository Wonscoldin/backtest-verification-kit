"""Invariant: every signal the live system skipped must be skipped for a reason the backtest also models.
(daily check since 2026-09-28)

Why: in a full live-vs-backtest audit, half of the mismatches found by hand were "live dropped the signal":
a price-drift guard rejecting 9-10 of 12 orders, a weekday filter silently discarding every Monday bar
(it left no trace -- now every skip is logged with a reason), Friday signals sent into a closed market.
The backtest measures signal -> entry, so any skip it does not model makes the plan optimistic by exactly
that much. Count skip reasons once a day; alert on any reason the backtest does not know.

RULES = (regex, category, backtest_models_it, account prefixes or None). An unmatched reason is
"unclassified" = NOT modelled -- if unknown meant fine, this monitor would rot towards silence.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

RULES: List[Tuple[str, str, bool, Optional[Tuple[str, ...]]]] = [
    # specific before general: occupancy by the ranking strategy is NOT modelled, plain occupancy is
    (r"occupied by another strategy: [^)]*momentum", "occupied by momentum (backtest does not block)", False, None),
    (r"symbol occupied", "symbol occupied (modelled)", True, None),
    (r"concurrency cap", "concurrency cap (modelled)", True, None),
    (r"portfolio exposure cap", "exposure cap (modelled)", True, None),
    (r"directional cap", "long-direction cap (modelled)", True, ("FirmA", "FirmB")),
    (r"^weekday blocked", "weekday filter (modelled)", True, None),
    (r"expiry deferred -- weekend closure", "weekend expiry deferral (modelled)", True, ("FirmB",)),
    (r"group concurrency cap", "correlated-group cap (modelled)", True, ("FirmB",)),
    (r"daily equity breaker", "daily breaker (modelled)", True, ("FirmA",)),
    # ---- losses the backtest does not know ----
    (r"price drift", "drift rejection", False, None),
    (r"spread cap .* exceeded", "spread too wide", False, None),
    (r"spec lookup failed", "instrument spec lookup failed", False, None),
    (r"fetch failed|no bars|empty response", "price feed failed", False, None),
    (r"equity read failed", "equity read failed", False, None),
    (r"10018|market closed", "market closed", False, None),
    (r"10031|no connection", "broker disconnected", False, None),
    (r"no stop price|stop undefined", "stop undefined", False, None),
    (r"below minimum lot", "below minimum lot", False, None),
    (r"opposite position|cross_account", "cross-account opposite-position guard", False, None),
]

RETRYABLE = ("10018", "market closed", "10031", "no connection")   # the runner retries these within the bar


def classify(reason: str, account: str = "") -> Tuple[str, bool]:
    text = str(reason or "")
    for pat, cat, modeled, accts in RULES:
        if re.search(pat, text, flags=re.I):
            if accts is not None and not any(str(account or "").startswith(a) for a in accts):
                return cat + " (not modelled for this account)", False   # modelled only where the backtest has it
            return cat, modeled
    return "unclassified", False


def _ts(rec: dict) -> Optional[datetime]:
    raw = rec.get("logged_at") or rec.get("tick_at")
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _read_jsonl(path: str) -> Iterable[dict]:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def collect(decision_paths: Iterable[str], *, since: datetime) -> dict:
    """Count skip reasons by (account, category) in the window, plus placed orders for ratios."""
    decision_paths = list(decision_paths)
    skips: Dict[Tuple[str, str, bool], int] = {}
    examples: Dict[Tuple[str, str, bool], str] = {}
    placed: Dict[str, int] = {}

    def add(acct, reason):
        cat, modeled = classify(reason, acct)
        k = (acct, cat, modeled)
        skips[k] = skips.get(k, 0) + 1
        examples.setdefault(k, str(reason)[:160])

    # Transient rejections are retried by the runner. If a retry placed the same account/symbol within 6h,
    # nothing was lost -- without this the weekly broker maintenance raised a false alarm every Saturday.
    pending: List[Tuple[str, str, datetime, str]] = []
    place_times: Dict[Tuple[str, str], List[datetime]] = {}
    for p in decision_paths:
        for r in _read_jsonl(p):
            if r.get("event") != "decision":
                continue
            t = _ts(r)
            if t is None or t < since:
                continue
            acct = r.get("account") or "(no account)"
            if r.get("action") == "PLACE":
                placed[acct] = placed.get(acct, 0) + 1
                place_times.setdefault((acct, str(r.get("symbol") or "")), []).append(t)
            elif r.get("skipped_reason"):
                reason = str(r["skipped_reason"])
                if any(k in reason for k in RETRYABLE):
                    pending.append((acct, str(r.get("symbol") or ""), t, reason))
                else:
                    add(acct, reason)
    for acct, sym, t, reason in pending:
        if not any(t < pt <= t + timedelta(hours=6) for pt in place_times.get((acct, sym), [])):
            add(acct, reason)
    return {"skips": skips, "examples": examples, "placed": placed,
            "false_occupancy": false_occupancy(decision_paths, since=since)}


_FALSE_OCC_SKIP_LEGS = ("bos", "s5", "cbp4h", "momentum")   # intraday strategies have a re-entry cooldown in the backtest too
_TERMINAL_RESTING = ("filled", "cancelled", "expired")


def false_occupancy(decision_paths: Iterable[str], *, since: datetime,
                    lookback: timedelta = timedelta(hours=48)) -> List[str]:
    """Skips logged as 'symbol occupied' when nothing actually occupied the symbol.

    Why: a silver long signal was dropped as "symbol occupied" one minute after the previous silver position's
    stop-out had been recorded -- the cooldown was counted from the discovery time. Three monitors accepted it
    because "occupied" is a reason the backtest knows; none checked whether the reason was TRUE.
    A Friday-bar signal only gets one Saturday tick, so the entry was simply lost.
    Rule (journal only): same account family and symbol, a 'closed' outcome within `lookback` before the skip,
    no PLACE/fill after that close, and no unfinished resting limit placed before it -> false occupancy.
    When in doubt, do not alert: this targets exactly the "skipped right after a close" family."""
    events: Dict[Tuple[str, str], List[Tuple[datetime, str, str]]] = {}
    skips: List[Tuple[datetime, str, str, str]] = []
    for p in decision_paths:
        for r in _read_jsonl(p):
            t = _ts(r)
            if t is None:
                continue
            acct = str(r.get("account") or "")
            fam = acct.split("-")[0]
            sym = str(r.get("symbol") or "").upper()
            if not fam or not sym:
                continue
            ev = r.get("event")
            if ev == "outcome":
                events.setdefault((fam, sym), []).append((t, str(r.get("outcome")), str(r.get("attempt_id") or "")))
            elif ev == "decision" and r.get("action") == "PLACE":
                events.setdefault((fam, sym), []).append((t, "PLACE", str(r.get("attempt_id") or "")))
            elif (ev == "decision" and t >= since and "symbol occupied" in str(r.get("skipped_reason") or "")
                  and not any(k in acct.lower() for k in _FALSE_OCC_SKIP_LEGS)):
                skips.append((t, acct, sym, str(r.get("key") or "")))
    out, seen = [], set()
    for t, acct, sym, key in sorted(skips):
        evs = sorted(e for e in events.get((acct.split("-")[0], sym), []) if e[0] < t)
        closes = [e for e in evs if e[1] == "closed" and e[0] >= t - lookback]
        if not closes:
            continue
        tc = closes[-1][0]
        if any(e[1] in ("PLACE", "filled") for e in evs if e[0] > tc):
            continue
        done = {e[2] for e in evs if e[1] in _TERMINAL_RESTING and e[2]}
        if any(e[1] == "PLACE" and e[2] and e[2] not in done and e[0] >= t - timedelta(hours=72)
               for e in evs if e[0] <= tc):
            continue
        k = (acct, sym, key)
        if k in seen:
            continue
        seen.add(k)
        out.append(f"{acct} {sym}: false occupancy -- signal at {t:%m-%d %H:%M} UTC skipped as 'symbol occupied', "
                   f"but the position closed at {tc:%m-%d %H:%M} and nothing was held or resting after that")
    return out


def report(data: dict) -> Tuple[List[str], List[str]]:
    """(lines the backtest does NOT know -> alert, lines it knows -> summary)."""
    bad, ok = list(data.get("false_occupancy") or []), []
    for (acct, cat, modeled), n in sorted(data["skips"].items(), key=lambda kv: (-kv[1], kv[0])):
        line = f"{acct} · {cat}: {n}"
        if modeled:
            ok.append(line)
        else:
            bad.append(f"{line} -- e.g. {data['examples'][(acct, cat, modeled)]}")
    return bad, ok
