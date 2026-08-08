#!/usr/bin/env python3
"""kalshi_trades_ticker_inventory.py — L292's "one-line ticker-inventory grep", made a tool.

L292 (2026-08-06, kalshi-edge-hunter Q21 round #24, producer + independent `verifier`):

    "A `tape/kalshi_trades/`-anchored maker/taker candidate must name its target tickers'
    PRESENCE on the trade tape at proposal time — the only committed day (`dt=2026-08-03`)
    is sports+crypto-only, so any econ/weather/politics markout-filter candidate is
    UNMEASURABLE today ... check the ticker inventory of the committed trade tape BEFORE
    proposing, not after."

That row's enforcement cell said "no machine-checkable artifact fits it ... the check is a
one-line ticker-inventory grep the proposing run must run". A discipline that lives only in
a lesson row is exactly the thing CLAUDE.md's third prime directive forbids ("invariants over
memory"): the S80/S81 fold on 2026-08-06 was caught by hand, and the NEXT one is one tired
round away. Two halves are mechanizable and neither touches a collector write path:

  1. THIS FILE — a read-only inventory of `tape/kalshi_trades/`, per SERIES, so the grep is
     one reproducible command with a stable JSON shape instead of a hand-rolled pipeline.
  2. `scripts/invariants.py::kalshi_trades_registration_surface_warning` — a non-gating
     advisory that reads `kb/strategies/00-index.md`, finds every registry row whose text
     anchors on `kalshi_trades`, and reports whether the KX series tokens that row names are
     actually present in this inventory.

WHAT A "COVERED" VERDICT MEANS, EXACTLY (the honesty that makes this usable):

  * The universe here is COMMITTED TAPE, never the platform and never the collector's
    capability. `collection/kalshi_trades.py` is ticker-scoped by construction (venue-wide
    density is ~1e6 prints/day, so a venue-wide pull is forbidden), and the one committed
    day was a stride-13 sample of 200 of the 2,713 tickers in `orderbook_depth/dt=2026-08-03`.
    So `ABSENT` reads "no committed print exists for this family, therefore a markout /
    toxicity / signed-flow statistic on it is UNMEASURABLE TODAY" — it does NOT read "Kalshi
    has no prints there" and it does NOT read "the collector cannot capture it".
  * `n_days` is reported on every verdict for that reason. An absence measured over ONE day
    is a floor statement about the tape, and the report says so in `coverage_note` rather
    than leaving the reader to remember it (L155: a low issue count is precision evidence,
    never recall).
  * Prefix matching is deliberately GENEROUS (a named token matches a series that merely
    starts with it, so `KXCPI` would match a hypothetical `KXCPICORE`). That biases the
    check toward NOT flagging: it can under-report an uncovered family, it can never
    manufacture an uncovered verdict for a family that is really there.

Read-only, fully offline, no network, no credentials. Never imported by a collector.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
TRADE_FAMILY = "kalshi_trades"

# A Kalshi market ticker is `SERIES-<event token>-<outcome token>`; the series is the prefix
# before the first hyphen (`KXAFLGAME-26AUG060530NMKBUL-BUL` -> `KXAFLGAME`). Verified against
# every one of the 42 distinct tickers on dt=2026-08-03.
_SERIES_RE = re.compile(r"^([A-Z0-9]+)-")

# Series tokens as they appear in prose: `KXCPI`, `KXCPI*`, `KXMLBGAME-26AUG03...`. The token
# is the leading uppercase-alnum run after `KX`; anything after a hyphen/star is event scope.
SERIES_TOKEN_RE = re.compile(r"\bKX[A-Z0-9]+")

# Families whose PRINTS the trade tape is known to carry today, kept only as documentation of
# what the 2026-08-03 pull actually contained. NOTHING reads this for a verdict — the verdict
# is always recomputed from tape, so this constant cannot silently go stale into a false
# "covered" (the failure mode a hardcoded allowlist would introduce).
KNOWN_2026_08_03_SERIES_NOTE = (
    "dt=2026-08-03: 39,698 prints / 42 tickers / 20 series, all sports or crypto "
    "(KXBTC/KXETH); 0 econ (KXCPI*/KXNFP*/KXGDP*/KXFED*/KXPCE*) prints — L292."
)


def series_of(ticker: Optional[str]) -> Optional[str]:
    """`KXMLBGAME-26AUG03DETCLE-DET` -> `KXMLBGAME`. None when there is no series to read.

    Refuses rather than guesses (the `extract_completeness` posture): a ticker with no hyphen
    has no separable series token, and inventing one would put a fabricated family into the
    inventory a registration check then trusts."""
    if not isinstance(ticker, str):
        return None
    m = _SERIES_RE.match(ticker.strip())
    return m.group(1) if m else None


def _day_of(path: Path) -> Optional[str]:
    stem = path.stem
    return stem.split("=", 1)[1] if stem.startswith("dt=") else None


def _family_files(tape_root: Path, max_day: Optional[str] = None,
                  min_day: Optional[str] = None) -> List[Path]:
    """Committed day-files of the trade family, optionally windowed on BOTH ends.

    `min_day` added 2026-08-08 (L316). A one-sided `max_day` closes L140's time-bomb only
    against tape that grows FORWARD. `tape/kalshi_trades/` has no scheduled writer (L313), so
    the way it actually grows is a BACKFILL — the 2026-08-08 phase-1 pull added
    dt=2026-07-07..07-12, all of which sit UNDER an 08-03 `max_day` and silently entered every
    window that had been frozen against exactly this kind of drift.
    """
    d = tape_root / TRADE_FAMILY
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("dt=*.jsonl")):
        day = _day_of(p)
        if day is None:
            continue
        if max_day is not None and day > max_day:
            continue
        if min_day is not None and day < min_day:
            continue
        out.append(p)
    return out


def trade_tape_inventory(tape_root: Path = ROOT / "tape",
                         max_day: Optional[str] = None,
                         min_day: Optional[str] = None) -> Dict[str, Any]:
    """Per-series inventory of `tape/kalshi_trades/`. Read-only; no network.

    `max_day`/`min_day` freeze the window at `dt=` strings (L140's time-bomb discipline — a
    test that pins real numbers must be able to close its window, or it rots as new tape
    lands). BOTH ends matter (L316): this family grows by backfill, so a day newer than
    nothing and older than `max_day` can still appear after a pin was written.

    Returns `n_days == 0` with an empty `series` map when the family is absent. That is an
    honest "no claim": every downstream verdict is `UNKNOWN_NO_TAPE`, never `ABSENT`, because
    an un-collected family and a collected-but-empty one are different claims (L289/L296)."""
    files = _family_files(tape_root, max_day, min_day)
    per_series_prints: Dict[str, int] = defaultdict(int)
    per_series_tickers: Dict[str, set] = defaultdict(set)
    per_series_days: Dict[str, set] = defaultdict(set)
    days: set = set()
    n_lines = 0
    n_malformed = 0
    n_no_ticker = 0
    n_unparsable_series = 0
    for path in files:
        day = _day_of(path)
        try:
            fh = open(path, "r", encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    n_malformed += 1
                    continue
                if not isinstance(rec, dict):
                    n_malformed += 1
                    continue
                n_lines += 1
                days.add(day)
                ticker = rec.get("ticker") or rec.get("market_ticker")
                if not isinstance(ticker, str) or not ticker:
                    n_no_ticker += 1
                    continue
                s = series_of(ticker)
                if s is None:
                    n_unparsable_series += 1
                    continue
                per_series_prints[s] += 1
                per_series_tickers[s].add(ticker)
                per_series_days[s].add(day)
    series = {
        s: {
            "n_prints": per_series_prints[s],
            "n_tickers": len(per_series_tickers[s]),
            "days": sorted(d for d in per_series_days[s] if d),
        }
        for s in sorted(per_series_prints, key=lambda k: (-per_series_prints[k], k))
    }
    day_list = sorted(d for d in days if d)
    return {
        "family": TRADE_FAMILY,
        "n_days": len(day_list),
        "days": day_list,
        "n_lines": n_lines,
        "n_malformed": n_malformed,
        "n_lines_without_ticker": n_no_ticker,
        "n_tickers_without_parsable_series": n_unparsable_series,
        "n_series": len(series),
        "n_tickers": sum(len(v) for v in per_series_tickers.values()),
        "series": series,
        "coverage_note": (
            "Universe = COMMITTED TAPE ONLY. collection/kalshi_trades.py is ticker-scoped by "
            "construction (venue-wide density ~1e6 prints/day), so an absent series means "
            "'unmeasurable from committed tape', never 'Kalshi has no prints there' and never "
            "'the collector cannot capture it'. Read every verdict against n_days above: an "
            "absence measured over one day is a floor statement (L155/L292)."
        ),
    }


# --------------------------------------------------------------------------- #
# coverage verdicts
# --------------------------------------------------------------------------- #
COVERED = "COVERED"
ABSENT = "ABSENT"
UNKNOWN_NO_TAPE = "UNKNOWN_NO_TAPE"
ALL_COVERAGE_VERDICTS: Tuple[str, ...] = (COVERED, ABSENT, UNKNOWN_NO_TAPE)


def series_coverage(inventory: Dict[str, Any], token: str) -> Dict[str, Any]:
    """Is `token` (a series name or a series PREFIX, e.g. `KXCPI` for `KXCPI*`) present?

    Prefix matching is deliberately generous — see the module docstring. It can under-report
    an absence; it can never invent one."""
    tok = (token or "").strip().rstrip("*")
    if not inventory.get("n_days"):
        return {"token": token, "verdict": UNKNOWN_NO_TAPE, "matched_series": [],
                "n_prints": 0}
    matched = sorted(s for s in inventory.get("series", {})
                     if s == tok or (tok and s.startswith(tok)))
    n_prints = sum(inventory["series"][s]["n_prints"] for s in matched)
    return {
        "token": token,
        "verdict": COVERED if matched else ABSENT,
        "matched_series": matched,
        "n_prints": n_prints,
    }


def named_series_tokens(text: str) -> List[str]:
    """Every distinct `KX...` series token named in a block of prose, sorted.

    Deliberately NOT a general ticker parser: it takes the leading series run only, so
    `KXFEDDECISION-26SEP-H0` and `KXFEDDECISION` collapse to one token — the family is the
    unit the trade collector covers or does not."""
    if not isinstance(text, str):
        return []
    return sorted(set(SERIES_TOKEN_RE.findall(text)))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-root", default=str(ROOT / "tape"))
    ap.add_argument("--min-day", default=None,
                    help="freeze the window's OLDER end at a dt= day (L316: this family grows "
                         "by backfill, so a max-day-only window does not stay frozen)")
    ap.add_argument("--max-day", default=None,
                    help="restrict to dt=<=DAY (freeze the window; L140)")
    ap.add_argument("--check", nargs="*", default=None, metavar="KXSERIES",
                    help="series token(s) to coverage-check against the inventory")
    ap.add_argument("--json", action="store_true", help="emit the raw report as JSON")
    args = ap.parse_args(argv)

    inv = trade_tape_inventory(Path(args.tape_root), args.max_day, args.min_day)
    checks = [series_coverage(inv, t) for t in (args.check or [])]
    if args.json:
        print(json.dumps({"inventory": inv, "checks": checks}, indent=2, sort_keys=True))
        return 0
    print(f"tape/{TRADE_FAMILY}/ — {inv['n_lines']} print(s) / {inv['n_tickers']} ticker(s) / "
          f"{inv['n_series']} series over {inv['n_days']} committed day(s) "
          f"{inv['days'] or ''}")
    if inv["n_malformed"] or inv["n_lines_without_ticker"] or inv["n_tickers_without_parsable_series"]:
        print(f"  malformed={inv['n_malformed']} no_ticker={inv['n_lines_without_ticker']} "
              f"unparsable_series={inv['n_tickers_without_parsable_series']}")
    for s, v in inv["series"].items():
        print(f"  {s:<24} {v['n_prints']:>7} prints  {v['n_tickers']:>3} tickers  "
              f"days={','.join(v['days'])}")
    for c in checks:
        print(f"CHECK {c['token']:<20} {c['verdict']:<16} "
              f"matched={','.join(c['matched_series']) or '-'} prints={c['n_prints']}")
    print(f"  NOTE: {inv['coverage_note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
