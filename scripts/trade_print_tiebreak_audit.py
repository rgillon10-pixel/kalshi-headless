#!/usr/bin/env python3
"""trade_print_tiebreak_audit.py — L323's MEASUREMENT half, made a tool.

L323 (2026-08-09, Q54 two-agent verifier re-check) found that exact-timestamp ties in
`tape/kalshi_trades/` are resolved **by file read order** — deterministic, but an artifact
of how the tape was written rather than a rule anyone declared. Its own row records the
repair half (an explicit `trade_id`-ordered tie-break inside
`scripts/q54_s79_flow_continuation_probe.py::first_agreeing_print`) as deliberately NOT
buildable while that probe is sealed mid-verdict (L311).

This file is the other half, which nothing had: a way to MEASURE the exposure from committed
tape, and — the question L323's own text left open with the words "`trade_id`, *if monotonic
within a capture*" — to decide from data whether `trade_id` is actually an adequate explicit
tie-break key at all.

Three questions, each answered from committed tape only (no network, read-only):

  1. `tie_census`            — how many `(ticker, instant)` groups carry >1 print, how
                               many of those disagree on `yes_price`, and how big the
                               price disagreement is in cents. This bounds how much any
                               "first print at/after t" rule can move under a different
                               tie-break.
  2. `tiebreak_key_adequacy` — is `trade_id` present on every print, globally unique, and
                               does it TOTALLY ORDER every tied group? If any tied group has
                               a repeated `trade_id`, the key L323 proposed does not exist
                               and the repair must name a different one.
  3. `chronological_concordance` — the falsifiable check that keeps (2) honest. A key that
                               totally orders ties is not thereby the TRUE sequence. Over
                               consecutive print pairs whose `created_time` strictly
                               increases, a time-ordered id (e.g. a real UUIDv7, whose first
                               48 bits are a millisecond clock) agrees with clock order at a
                               rate near 1.0; a random id agrees at ~0.5. This measures that
                               rate instead of assuming it.

Run:
    python3 scripts/trade_print_tiebreak_audit.py                  # full committed tape
    python3 scripts/trade_print_tiebreak_audit.py --days dt=2026-07-07 dt=2026-07-08
    python3 scripts/trade_print_tiebreak_audit.py --json out.json

Honest limits (restated in every report's own `coverage_note` so they travel with any quoted
number):
  * The tie census is a property of ALREADY-COMMITTED append-only tape. It bounds the
    exposure of a print-selection rule; it can never say which tied print executed first.
  * `n_groups_price_differing` counts groups where a tie-break CAN change a selected price.
    It is an upper bound on realized impact for any given probe, because a probe may never
    select from that group (wrong ticker, outside its window, non-`broker_truth`, ...).
  * Adequacy is measured over the tape as committed TODAY. It is a ratchet input, not a
    permanent guarantee: a future backfill could introduce a duplicate `trade_id`, which is
    exactly why `tests/test_trade_print_tiebreak_audit.py` re-derives it rather than pinning
    a frozen answer.
  * Only `broker_truth` prints are admitted by default (`admitted_tag`), matching the
    admission rule every downstream probe already applies (`q51_maker_fillsim.load_prints`);
    a print carrying any other tag is not a venue-reported transaction and cannot be a fill.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.timeutil import parse_iso_utc  # noqa: E402

TRADES_TAPE = ROOT / "tape" / "kalshi_trades"

ADMITTED_TAG = "broker_truth"

# A print, reduced to the fields this audit needs. Kept as a tuple so a full-tape pass over
# ~2e5 records stays cheap.
#   (ticker, instant, trade_id, yes_price, file_index, line_index)
#
# The tie KEY and every ordering below use the PARSED instant, never the raw `created_time`
# string. On the committed tape the producer strips trailing zeros, so fractional-second
# precision varies from 1 to 6 digits (measured: 6d x192,208 / 5d x19,146 / 4d x1,878 /
# 3d x227 / 2d x26 / 1d x3). Two renderings of one instant would then be different strings —
# a silent UNDER-count of ties — and lexical order across differing precisions is simply wrong
# ("...:00.5Z" sorts AFTER "...:00.500001Z"). Parsing goes through
# `core.timeutil.parse_iso_utc`, not `datetime.fromisoformat`, because the stdlib call rejects
# fractional seconds that are not exactly 3 or 6 digits on older Pythons (L136/L138) — which is
# most of the ragged precisions this very tape carries. The instant is kept as the parsed
# `datetime`, not an epoch float: at 2026 epochs a float64 second resolves to only ~0.24us,
# which is coarser than the microsecond precision the tape actually carries, so a float key
# would merge two genuinely distinct instants into a manufactured "tie".
Print = Tuple[str, datetime, str, Optional[float], int, int]


def day_paths(tape_dir: Path = TRADES_TAPE,
              days: Optional[Sequence[str]] = None) -> List[Path]:
    """Committed `dt=*.jsonl` day-files, oldest first. `days` filters by stem
    (`dt=2026-07-07`, with or without the `.jsonl` suffix)."""
    if not tape_dir.exists():
        return []
    paths = sorted(tape_dir.glob("dt=*.jsonl"))
    if days is None:
        return paths
    wanted = {d[:-6] if d.endswith(".jsonl") else d for d in days}
    return [p for p in paths if p.stem in wanted]


def iter_prints(paths: Iterable[Path],
                admitted_tag: Optional[str] = ADMITTED_TAG) -> Iterator[Print]:
    """Yield reduced prints in FILE ORDER — deliberately, because file order is the
    incidental tie-break L323 is about; `file_index`/`line_index` are what make the
    "what does read order currently pick" question answerable."""
    for fi, path in enumerate(paths):
        with open(path, "r", encoding="utf-8") as fh:
            for li, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if admitted_tag is not None and rec.get("price_source_tag") != admitted_tag:
                    continue
                tk, ct = rec.get("ticker"), rec.get("created_time")
                if not tk or not ct:
                    continue
                try:
                    inst = parse_iso_utc(str(ct))
                except Exception:
                    continue
                yp = rec.get("yes_price")
                yp = float(yp) if isinstance(yp, (int, float)) else None
                yield (str(tk), inst, str(rec.get("trade_id") or ""), yp, fi, li)


def tie_census(prints: Sequence[Print]) -> Dict[str, Any]:
    """Exact-timestamp tie structure over the `(ticker, created_time)` key — the key every
    "first print at/after t" rule implicitly has to break."""
    groups: Dict[Tuple[str, datetime], List[Print]] = collections.defaultdict(list)
    for p in prints:
        groups[(p[0], p[1])].append(p)

    n_groups_tied = 0
    n_prints_in_ties = 0
    n_groups_price_differing = 0
    n_prints_in_price_differing = 0
    max_group_size = 0
    spreads: List[float] = []
    for members in groups.values():
        k = len(members)
        if k > max_group_size:
            max_group_size = k
        if k < 2:
            continue
        n_groups_tied += 1
        n_prints_in_ties += k
        prices = {m[3] for m in members if m[3] is not None}
        if len(prices) > 1:
            n_groups_price_differing += 1
            n_prints_in_price_differing += k
            spreads.append(round((max(prices) - min(prices)) * 100.0, 6))

    spreads.sort()

    def pct(q: float) -> Optional[float]:
        if not spreads:
            return None
        idx = min(len(spreads) - 1, max(0, int(round(q * (len(spreads) - 1)))))
        return spreads[idx]

    n = len(prints)
    return {
        "n_prints": n,
        "n_distinct_keys": len(groups),
        "n_groups_tied": n_groups_tied,
        "n_prints_in_ties": n_prints_in_ties,
        "frac_prints_in_ties": round(n_prints_in_ties / n, 6) if n else None,
        "n_groups_price_differing": n_groups_price_differing,
        "n_prints_in_price_differing_groups": n_prints_in_price_differing,
        "max_group_size": max_group_size,
        "price_spread_cents": {
            "n": len(spreads),
            "min": spreads[0] if spreads else None,
            "p50": pct(0.50),
            "p90": pct(0.90),
            "max": spreads[-1] if spreads else None,
        },
    }


def tiebreak_key_adequacy(prints: Sequence[Print]) -> Dict[str, Any]:
    """Is `trade_id` an adequate EXPLICIT tie-break key (L323's proposed repair)?

    Adequate == present on every print AND distinct within every tied group (so it totally
    orders each group). Global uniqueness is reported separately: it is a stronger property
    than the repair needs, but a global collision is a tape-integrity signal worth surfacing.
    """
    missing = sum(1 for p in prints if not p[2])
    counts: Dict[str, int] = collections.Counter(p[2] for p in prints if p[2])
    global_dupes = [t for t, c in counts.items() if c > 1]

    groups: Dict[Tuple[str, datetime], List[str]] = collections.defaultdict(list)
    for p in prints:
        groups[(p[0], p[1])].append(p[2])
    non_ordering = 0
    for ids in groups.values():
        if len(ids) < 2:
            continue
        if len(set(ids)) != len(ids):
            non_ordering += 1

    adequate = (missing == 0 and non_ordering == 0)
    return {
        "field": "trade_id",
        "n_prints": len(prints),
        "n_missing_or_empty": missing,
        "n_distinct": len(counts),
        "n_globally_duplicated_ids": len(global_dupes),
        "n_tied_groups_not_totally_ordered": non_ordering,
        "totally_orders_every_tie": adequate,
        "verdict": ("ADEQUATE — trade_id is present on every admitted print and distinct "
                    "within every tied group, so it can serve as a declared tie-break key"
                    if adequate else
                    "INADEQUATE — trade_id cannot totally order every tie; L323's proposed "
                    "repair needs a different key"),
    }


def chronological_concordance(prints: Sequence[Print]) -> Dict[str, Any]:
    """Does `trade_id` order agree with clock order? (Falsifies "explicit key == true order".)

    Within each ticker, walk consecutive pairs of prints in `created_time` order and count how
    often `trade_id` order agrees. `rate` near 1.0 ⇒ the id encodes time (UUIDv7-like) and a
    trade_id sort recovers the real sequence; `rate` near 0.5 ⇒ the id is effectively random,
    so an explicit trade_id tie-break buys DECLAREDNESS and reproducibility, not chronological
    truth.

    METHOD NOTE (a real artifact this function was built with and then fixed — it is the
    reason the measurement is trustworthy). Only prints that are the SOLE print at their
    `(ticker, created_time)` key are used. Including tied prints biases the statistic below
    0.5 for a purely random id: any sort that orders a tie group by trade_id makes that
    group's last member a max-of-k draw, which then loses its comparison against the next
    (unconditioned) id more often than chance. Measured on the real tape, the biased version
    read 0.412 and the singleton-only version reads ~0.5 — the same data, one of the two
    numbers manufactured by the estimator. L27/L165's class of error, caught in-build.
    """
    by_ticker: Dict[str, List[Tuple[datetime, str]]] = collections.defaultdict(list)
    key_counts: Dict[Tuple[str, datetime], int] = collections.Counter(
        (p[0], p[1]) for p in prints)
    for p in prints:
        if p[2] and key_counts[(p[0], p[1])] == 1:
            by_ticker[p[0]].append((p[1], p[2]))

    pairs = 0
    concordant = 0
    for rows in by_ticker.values():
        rows.sort(key=lambda r: r[0])
        for a, b in zip(rows, rows[1:]):
            if a[0] >= b[0]:
                continue
            pairs += 1
            if a[1] < b[1]:
                concordant += 1

    rate = round(concordant / pairs, 6) if pairs else None
    if rate is None:
        interp = "UNDETERMINED — no strictly-increasing consecutive singleton pairs"
    elif rate >= 0.95:
        interp = "TIME-ORDERED — trade_id order tracks clock order; a trade_id sort recovers sequence"
    elif rate <= 0.05:
        interp = ("REVERSE-ORDERED — trade_id order runs opposite to clock order; an "
                  "unexpected shape worth investigating before relying on the key")
    elif 0.40 <= rate <= 0.60:
        interp = ("RANDOM — trade_id order is independent of clock order; an explicit "
                  "trade_id tie-break is DECLARED and reproducible but NOT chronological")
    else:
        interp = "PARTIAL — trade_id order is correlated with, but not determined by, clock order"
    return {
        "field": "trade_id",
        "pairs_source": "untied singleton prints only (see METHOD NOTE)",
        "n_strictly_increasing_pairs": pairs,
        "n_concordant": concordant,
        "rate": rate,
        "interpretation": interp,
    }


def build_report(tape_dir: Path = TRADES_TAPE,
                 days: Optional[Sequence[str]] = None,
                 admitted_tag: Optional[str] = ADMITTED_TAG) -> Dict[str, Any]:
    paths = day_paths(tape_dir, days)
    prints = list(iter_prints(paths, admitted_tag=admitted_tag))
    census = tie_census(prints)
    adequacy = tiebreak_key_adequacy(prints)
    concord = chronological_concordance(prints)
    return {
        "lesson": "L323",
        "tape_dir": str(tape_dir),
        "days": [p.stem for p in paths],
        "n_days": len(paths),
        "admitted_price_source_tag": admitted_tag,
        "tie_census": census,
        "tiebreak_key_adequacy": adequacy,
        "chronological_concordance": concord,
        "coverage_note": (
            "Read-only over committed append-only tape; no network. "
            "n_groups_price_differing is an UPPER bound on any single probe's realized "
            "tie-break exposure (a probe may never select from a given group). Adequacy is "
            "measured over the tape as committed today, not guaranteed for future backfills. "
            "A key that totally orders ties is not the true execution sequence — see "
            "chronological_concordance. Only price_source_tag=="
            f"{admitted_tag!r} prints are admitted."
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-dir", default=str(TRADES_TAPE))
    ap.add_argument("--days", nargs="*", default=None,
                    help="day stems to restrict to, e.g. dt=2026-07-07")
    ap.add_argument("--all-tags", action="store_true",
                    help="admit every price_source_tag (default: broker_truth only)")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="also write the report to this path")
    args = ap.parse_args(argv)

    rep = build_report(Path(args.tape_dir), args.days,
                       admitted_tag=None if args.all_tags else ADMITTED_TAG)
    text = json.dumps(rep, indent=1, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
