#!/usr/bin/env python3
"""gen_data_map.py — regenerate DATA-MAP.md, the single orientation document for the
committed tape corpus.

Why this exists: the project's stated plan is to keep collecting autonomously for months
and periodically point fresh (frontier-model) analysts at the corpus. A model arriving
cold should orient in ONE read — what each family captures, how big/continuous it is,
what price-source tags it carries, and which strategy questions it feeds — instead of
spelunking 28 directories. The audit that motivated this (2026-07-22) found gaps nobody
noticed for two weeks precisely because no single document showed the whole corpus.

Honesty posture: every per-family statistic in the generated document is COMPUTED from
the committed tape at generation time (file counts, date ranges, line counts, missing
days, sampled price_source_tag distribution) — never hand-typed. The only hand-curated
part is the ANNOTATIONS table (purpose / status / consumers), and a family present on
disk but missing from ANNOTATIONS is rendered as `UNANNOTATED` — visible drift, never a
silent omission. Regenerate with:

    python scripts/gen_data_map.py            # rewrites DATA-MAP.md in place
    python scripts/gen_data_map.py --check    # exit 1 if DATA-MAP.md is stale (CI-able)

Read-only over tape/; writes only DATA-MAP.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TAPE_ROOT = REPO_ROOT / "tape"
DEFAULT_OUT = REPO_ROOT / "DATA-MAP.md"

# Lines sampled per family (newest file) for the tag/field summary — a bounded read so
# regeneration stays fast even when a family holds hundreds of MB.
SAMPLE_LINES = 500

# Hand-curated layer: purpose, lifecycle status, and consumers per family. A family on
# disk that is absent here renders as UNANNOTATED (drift made visible). Statuses:
#   active     — a live collector appends on a schedule
#   one-shot   — deliberate single capture / backfill cache (not for time-series stats)
#   superseded — intentionally stopped; named successor
#   dormant    — collector exists but its universe is currently empty/out-of-season
ANNOTATIONS: Dict[str, Dict[str, str]] = {
    "anomalies": {"status": "active", "purpose": "Daily platform-wide sweep for fee-clearing bracket/monotonicity violations (S3/Q6). NOTE 2026-07-22: audit found 99.97% of accumulated flags are ask=0 no-offer artifacts + cross-entity mis-nests — do NOT mine this family for candidates until the sweep's grouping is fixed.", "feeds": "S3, Q6"},
    "crypto_hourly": {"status": "active", "purpose": "Hourly BTC/ETH bracket books near settlement + Coinbase spot + settle outcomes. Generation-starved since ~07-14 (Kalshi lists fewer hourly brackets).", "feeds": "S8, S10, Q7"},
    "crypto_hourly_historical_spot": {"status": "one-shot", "purpose": "Coinbase spot backfill supporting crypto_hourly joins.", "feeds": "S8"},
    "econ_prints": {"status": "active", "purpose": "Daily econ-event ladders (CPI/jobs/Fed) + Atlanta Fed nowcasts + settlement joins.", "feeds": "S2, S17"},
    "hf_burst": {"status": "one-shot", "purpose": "High-frequency burst probe capture (single session).", "feeds": "Q25"},
    "hyperliquid_funding": {"status": "active", "purpose": "Incremental Hyperliquid BTC/ETH hourly funding prints (off-venue leg for the funding-clamp lane).", "feeds": "Q42, Q43"},
    "orderbook_depth": {"status": "active", "purpose": "Hourly L2 depth snapshots for every ticker the pass discovers — the richest microstructure family.", "feeds": "S6, Q25, Q26, OBS-1"},
    "perp_tape": {"status": "active", "purpose": "Kalshi crypto PERP venue: contract list, BTC/ETH L2, live funding estimates, finalized funding prints. Carries the funding-clamp anomaly (Kalshi pins funding to 0 in ~91-100% of snapshots; offshore never does).", "feeds": "Q42, Q43"},
    "polymarket_cpi_pairs": {"status": "active", "purpose": "CPI bucket pairing Kalshi<->Polymarket. WARNING: the Kalshi leg is a SYNTHETIC derived_prob and is degenerate for exact/ceiling buckets (|prob_gap|>1 rows exist) — never treat its gap as fillable.", "feeds": "Q32-adjacent econ pairing"},
    "polymarket_macro_pairs": {"status": "active", "purpose": "Fed-decision buckets on both venues at real asks + gap. Both legs real_ask.", "feeds": "Q31, S34 (dead), FOMC watch"},
    "polymarket_pairs": {"status": "superseded", "purpose": "First-generation World-Cup cross-venue pairs. Stopped 2026-07-15 when the WC champion market resolved (legitimate zero-match, tracked as known_benign_silence in tape_gap_monitor). Successors: polymarket_macro_pairs, polymarket_cpi_pairs.", "feeds": "S34 (dead)"},
    "q26_settlement_cache": {"status": "one-shot", "purpose": "Legacy per-probe settlement cache; folded into settlement_ledger (Q45 migration), kept for reproducibility.", "feeds": "Q26"},
    "q27_settlement_cache": {"status": "one-shot", "purpose": "Legacy per-probe settlement cache; folded into settlement_ledger.", "feeds": "Q27"},
    "q29_settlement_cache": {"status": "one-shot", "purpose": "Legacy per-probe settlement cache; folded into settlement_ledger.", "feeds": "Q29"},
    "q30_settlement_cache": {"status": "one-shot", "purpose": "Legacy per-probe settlement cache; folded into settlement_ledger.", "feeds": "Q30"},
    "q42_hl_funding_cache": {"status": "one-shot", "purpose": "Hyperliquid funding-history backfill, 13 coins x ~1,042 hourly prints (broker_truth).", "feeds": "Q42"},
    "s14_ladder_fillsim": {"status": "one-shot", "purpose": "Queue-fill simulation output that falsified S14's maker proxy (Q34).", "feeds": "S14 (dead)"},
    "seed5_funding_cache": {"status": "one-shot", "purpose": "OKX funding snapshot (third-venue funding reference).", "feeds": "Q42"},
    "settlement_ledger": {"status": "active", "purpose": "THE label set: daily platform-wide settled-market harvest (result/settlement_value, broker_truth, deduped, append-only). Kalshi purges settled markets ~60d after close (L11) — this family is what keeps y-variables from being lost. Froze silently 07-18..21 (L123); catch-up gating added 2026-07-22.", "feeds": "every backtest's y-variable; Q45"},
    "sports_clv": {"status": "one-shot", "purpose": "Closing-line-value join cache (early sports probes).", "feeds": "S7"},
    "sports_clv_s7": {"status": "one-shot", "purpose": "S7 CLV trade list cache.", "feeds": "S7"},
    "sports_history": {"status": "one-shot", "purpose": "Historical sports results cache.", "feeds": "S7"},
    "sports_history_s7": {"status": "one-shot", "purpose": "World Cup odds bulk source (xlsx + jsonl).", "feeds": "S7"},
    "sports_maker_fillsim": {"status": "one-shot", "purpose": "Maker fill-sim cache for sports probes.", "feeds": "Q24"},
    "sports_pairs": {"status": "active", "purpose": "Hourly sports moneyline BBO + de-vigged sharp-odds leg where the odds key is present. Longest continuous rich family. Legacy capture-*/raw.json blobs from 07-09/07-10 coexist with per-day jsonl (consolidation candidate).", "feeds": "S7, S11, Q24, Q27"},
    "universe_sweep": {"status": "active", "purpose": "Full open-universe top-of-book snapshot 4x/day (~10k markets/pass, real_ask inline BBOs) — the cross-sectional census for longshot-fade / stale-quote / overround studies.", "feeds": "Q46, longshot/overround census, OBS-1"},
    "weather_actuals": {"status": "active", "purpose": "Daily observed Tmax actuals (IEM ASOS + NWS CLI cross-confirm) joined to Kalshi settled weather markets — settlement truth for the weather-revival program.", "feeds": "Q36, Q37, Q38"},
    "weather_books": {"status": "active", "purpose": "Hourly full-depth temp-bracket books (floor/cap strikes). Youngest rich family; feeds the weather-revival gates (Q37 ~Aug 5).", "feeds": "Q36, Q37, Q38"},
}


def _family_stats(fam_dir: Path) -> Optional[Dict[str, Any]]:
    """Computed (never hand-typed) stats for one family dir. Returns None for a dir with
    no regular files at all."""
    dt_files = sorted(fam_dir.glob("dt=*.jsonl"))
    all_files = [p for p in fam_dir.rglob("*") if p.is_file()]
    if not all_files:
        return None
    size = sum(p.stat().st_size for p in all_files)
    days: List[str] = [p.name[len("dt="):-len(".jsonl")] for p in dt_files]
    n_lines = 0
    for p in dt_files:
        with p.open("rb") as fh:
            n_lines += sum(1 for _ in fh)
    missing: List[str] = []
    if len(days) >= 2:
        try:
            d0, d1 = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
            have = set(days)
            cur = d0
            while cur <= d1:
                if cur.isoformat() not in have:
                    missing.append(cur.isoformat())
                cur += timedelta(days=1)
        except ValueError:
            pass
    tags: Counter = Counter()
    schema_versions: set = set()
    fields: List[str] = []
    if dt_files:
        with dt_files[-1].open() as fh:
            for i, line in enumerate(fh):
                if i >= SAMPLE_LINES:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    tags["<unparseable>"] += 1
                    continue
                if not fields:
                    fields = sorted(rec.keys())
                if "schema_version" in rec:
                    schema_versions.add(str(rec["schema_version"]))
                tags[str(rec.get("price_source_tag", "<untagged>"))] += 1
    return {
        "n_dt_files": len(dt_files), "n_all_files": len(all_files), "size": size,
        "first_day": days[0] if days else None, "last_day": days[-1] if days else None,
        "n_lines": n_lines, "missing_days": missing,
        "tags": dict(tags), "schema_versions": sorted(schema_versions), "fields": fields,
    }


def _fmt_size(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n / 1.0:.1f}{unit}"
        n /= 1024
    return f"{n}B"


def render(tape_root: Path) -> str:
    fams = sorted(d for d in tape_root.iterdir() if d.is_dir())
    out: List[str] = []
    out.append("# DATA-MAP — the committed tape corpus, one read")
    out.append("")
    out.append("<!-- GENERATED by scripts/gen_data_map.py — do not hand-edit stats; edit")
    out.append("     ANNOTATIONS in the script and regenerate. `--check` verifies freshness. -->")
    out.append("")
    out.append("Every statistic below is computed from the committed tape at generation time.")
    out.append("Prose (purpose / status / consumers) is curated in `scripts/gen_data_map.py`.")
    out.append("Companion documents: `tape/README.md` (commit policy), `PROVENANCE.md` (trust")
    out.append("tags), `kb/strategies/00-index.md` (what the Sx/Qx consumers mean),")
    out.append("`scripts/tape_gap_monitor.py` (pipe-health monitor these stats feed).")
    out.append("Not covered here: `data/` (gitignored local bulk — see project CLAUDE.md) and")
    out.append("`paper/` (append-only paper-trading ledger).")
    out.append("")
    for fam in fams:
        st = _family_stats(fam)
        if st is None:
            continue
        ann = ANNOTATIONS.get(fam.name)
        status = ann["status"] if ann else "UNANNOTATED"
        out.append(f"## tape/{fam.name}/ — `{status}`")
        out.append("")
        if ann:
            out.append(f"{ann['purpose']}")
            out.append("")
            out.append(f"*Feeds:* {ann['feeds']}")
        else:
            out.append("UNANNOTATED — a collector added this family without registering it in")
            out.append("`scripts/gen_data_map.py::ANNOTATIONS`. Add purpose/status/feeds there.")
        out.append("")
        span = (f"{st['first_day']} → {st['last_day']}" if st["first_day"] else "no dt= files")
        out.append(f"- span: {span} · dt-files: {st['n_dt_files']} · lines: {st['n_lines']:,}"
                   f" · size: {_fmt_size(st['size'])} (all {st['n_all_files']} files)")
        if st["missing_days"]:
            miss = ", ".join(st["missing_days"][:8])
            more = f" (+{len(st['missing_days']) - 8} more)" if len(st["missing_days"]) > 8 else ""
            out.append(f"- missing days in span: {miss}{more}")
        if st["tags"]:
            tag_str = ", ".join(f"{k}: {v}" for k, v in sorted(st["tags"].items()))
            out.append(f"- price_source_tag (sample of newest file, ≤{SAMPLE_LINES} lines): {tag_str}")
        if st["schema_versions"]:
            out.append(f"- schema_version: {', '.join(st['schema_versions'])}")
        if st["fields"]:
            out.append(f"- fields (first sampled record): {', '.join(st['fields'])}")
        out.append("")
    disk = {f.name for f in fams}
    orphaned = sorted(set(ANNOTATIONS) - disk)
    if orphaned:
        out.append("## Annotated but absent on disk")
        out.append("")
        out.append(", ".join(orphaned))
        out.append("")
    return "\n".join(out) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Regenerate DATA-MAP.md from the committed tape.")
    ap.add_argument("--tape-root", default=str(DEFAULT_TAPE_ROOT))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the on-disk document differs from a fresh render (stale).")
    args = ap.parse_args(argv)
    doc = render(Path(args.tape_root))
    out_path = Path(args.out)
    if args.check:
        current = out_path.read_text() if out_path.exists() else ""
        if current != doc:
            print(f"[gen_data_map] {out_path} is stale — regenerate with: python scripts/gen_data_map.py",
                  file=sys.stderr)
            return 1
        print(f"[gen_data_map] {out_path} is fresh.")
        return 0
    out_path.write_text(doc)
    print(f"[gen_data_map] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
