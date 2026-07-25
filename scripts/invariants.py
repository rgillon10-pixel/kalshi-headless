#!/usr/bin/env python3
"""invariants.py — the 6 Hard Rules of CLAUDE.md as runnable assertions.

The project's prime directive #3: "Invariants over memory. Every hard lesson becomes a CI
assertion, not a note. The assert prevents the *next variant* of a bug; a memory file would
not." This file is that CI assertion. Each Hard Rule is encoded as either a regex check
(static, file-text level) or a SQLite probe (DB-state level). A failing invariant is a
structural regression — fix the code, not the rule.

Hard Rules (CLAUDE.md):
  #1 No `ncep_gefs025` in any model list (byte-identical to gfs_seamless).
  #2 No `pstdev(member_values)` without a member_count>=4 guard  -> route via core/stats.py.
  #3 No `yes_ask` treated as probability; always normalized_ask = yes_ask/bracket_sum
     -> the only sanctioned yes_ask/no_ask arithmetic site is core/pricing.py.
  #4 No synthetic-priced backtest may quote a P&L number without its price_source_tag
     -> DB: any table with a `pnl` column must carry a valid `price_source_tag`.
  #5 Kelly rho is regime-conditional {benign:0.05,mixed:0.25,frontal:0.60} — never static 0.4.
  #6 No FastAPI / HTTP servers.
Plus the trust=FALSE default: price_source_tag in {real_ask,broker_truth,midpoint,synthetic}.

Invocation modes:
  --pre-edit-hook   PreToolUse hook mode. Reads stdin JSON {tool_name, tool_input}. For
                    Write, scans the new content; for Edit, scans the post-edit content.
                    Exits 2 to BLOCK on any static violation. Single-file, fast.
  --full            Whole-tree scan of every .py/.sql under repo root. Exit 2 if any fail.
  --db PATH         Run DB invariants against the SQLite at PATH. Exit 2 if any fail.
  (no flag)         Same as --full.

Lines that legitimately contain a banned string (rule defs, fixtures) carry the sentinel
`# inv-pattern-def` and are skipped.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

SENTINEL = "inv-pattern-def"

EXCLUDE_DIRS = {".venv", "venv", "__pycache__", ".claude", ".git", "worktrees",
                ".pytest_cache", ".mypy_cache", "node_modules", "data"}

# The single source of truth for the valid tags lives in core/source_tag.py; mirrored here
# so the DB probe has no import-time dependency on the package being importable.
VALID_SOURCE_TAGS = ("real_ask", "broker_truth", "midpoint", "synthetic")

# Files allowed to contain banned patterns by purpose (the rule-definition files and the
# adversarial test fixtures). Relative to ROOT, POSIX separators.
EXCLUDE_FILES = {
    "scripts/invariants.py",        # this rule-definition file
    "tests/test_invariants.py",     # adversarial fixtures by design
}

# Per-rule sanctioned sites: the one file each rule's pattern is *expected* to live in.
SANCTIONED = {
    "pstdev": "core/stats.py",
    "yes_ask_arith": "core/pricing.py",
    "fee_rate": "core/pricing.py",
    "order_endpoints": "execution/kalshi_client.py",   # unbuilt until live-graduation nears
    "risk_caps": "execution/limits.py",
    "iso_parse": "core/timeutil.py",   # home of the tolerant parse_iso_utc (L136/L138/L150)
}


def _rel(path: Path) -> str:
    """Best-effort POSIX path relative to ROOT (robust to macOS case-insensitive FS)."""
    for base in (ROOT, ROOT.resolve()):
        try:
            return str((path if path.is_absolute() else base / path).resolve()
                       .relative_to(base)).replace("\\", "/")
        except ValueError:
            continue
    p_str, r_str = str(path), str(ROOT)
    if p_str.lower().startswith(r_str.lower() + "/"):
        return p_str[len(r_str) + 1:].replace("\\", "/")
    return str(path).replace("\\", "/")


def _file_excluded(path: Path) -> bool:
    if path.name == "invariants.py":
        return True
    return _rel(path) in EXCLUDE_FILES


def _is_inside_root(path: Path) -> bool:
    for base in (ROOT, ROOT.resolve()):
        try:
            (path.resolve()).relative_to(base)
            return True
        except ValueError:
            continue
    return str(path).lower().startswith(str(ROOT).lower() + "/")


def _iter_source_files(root: Path = ROOT, exts: Tuple[str, ...] = (".py", ".sql")) -> List[Path]:
    out = []
    for p in root.rglob("*"):
        if p.is_dir() or p.suffix not in exts:
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def _scan_lines(text: str) -> List[Tuple[int, str]]:
    """(lineno, line) pairs, skipping sentinel lines."""
    return [(i, ln) for i, ln in enumerate(text.splitlines(), 1) if SENTINEL not in ln]


def _fmt(path: Path, hits: List[Tuple[int, str]], rationale: str) -> str:
    head = f"{_rel(path)}: {rationale}"
    body = "\n".join(f"    {n:>4}  {ln.strip()}" for n, ln in hits[:5])
    if len(hits) > 5:
        body += f"\n    ... and {len(hits) - 5} more"
    return f"{head}\n{body}"


# ─── Static invariants ───────────────────────────────────────────────────────

def inv_no_gefs(path: Path, text: str) -> Optional[str]:
    """#1 No `ncep_gefs025` in a model list — byte-identical to gfs_seamless."""
    if _file_excluded(path):
        return None
    pat = re.compile(r'["\']ncep_gefs025["\']\s*[,:\]]')
    hits = [(i, ln) for i, ln in _scan_lines(text) if pat.search(ln)]
    return _fmt(path, hits, "ncep_gefs025 in a model list — duplicate of gfs_seamless (#1)") if hits else None


def inv_no_bare_pstdev(path: Path, text: str) -> Optional[str]:
    """#2 No bare `pstdev(` outside core/stats.py (must route via safe_pstdev's n>=4 guard)."""
    if _file_excluded(path) or _rel(path) == SANCTIONED["pstdev"]:
        return None
    pat = re.compile(r'\bpstdev\s*\(')
    hits = [(i, ln) for i, ln in _scan_lines(text) if pat.search(ln)]
    return _fmt(path, hits,
                "bare pstdev() — Hard Rule #2: use core.stats.safe_pstdev (enforces n>=4; "
                "pt1 mixed 3/5/150/255-member arrays)") if hits else None


def inv_no_pstdev_import(path: Path, text: str) -> Optional[str]:
    """#2b No `from statistics import pstdev` outside core/stats.py."""
    if _file_excluded(path) or _rel(path) == SANCTIONED["pstdev"]:
        return None
    pat = re.compile(r'from\s+statistics\s+import\s+[^\n#]*\bpstdev\b')
    hits = [(i, ln) for i, ln in _scan_lines(text) if pat.search(ln)]
    return _fmt(path, hits,
                "imports statistics.pstdev — route through core.stats.safe_pstdev (#2)") if hits else None


def inv_no_yes_ask_arithmetic(path: Path, text: str) -> Optional[str]:
    """#3 No `yes_ask`/`no_ask` arithmetic outside core/pricing.py (forces bracket_sum divisor)."""
    if _file_excluded(path) or _rel(path) == SANCTIONED["yes_ask_arith"]:
        return None
    pat = re.compile(
        r'\b(?:yes|no)_ask\s*[+\-*/%]'      # var followed by an arithmetic op
        r'|[+\-*/%]\s*(?:yes|no)_ask\b'     # arithmetic op followed by var
    )
    hits = [(i, ln) for i, ln in _scan_lines(text) if pat.search(ln)]
    return _fmt(path, hits,
                "yes_ask/no_ask arithmetic — Hard Rule #3: use core.pricing.normalized_ask "
                "(forces the bracket_sum divisor; raw ask ignores the overround)") if hits else None


def inv_no_static_rho_point_four(path: Path, text: str) -> Optional[str]:
    """#5 No static Kelly rho literal 0.4 — must be regime-conditional."""
    if _file_excluded(path):
        return None
    pat = re.compile(r'\b(?:[A-Z_]*RHO|rho)\s*=\s*0\.4\b')
    hits = [(i, ln) for i, ln in _scan_lines(text)
            if pat.search(ln) and not ln.lstrip().startswith("#")]
    return _fmt(path, hits,
                "static rho=0.4 — Hard Rule #5: use regime-conditional rho "
                "{benign:0.05,mixed:0.25,frontal:0.60}") if hits else None


def inv_no_handrolled_fee_rate(path: Path, text: str) -> Optional[str]:
    """L5 No hand-rolled Kalshi fee-rate literal outside core/pricing.py. The fee schedule
    rates (taker 0.07, maker 0.0175, S&P/NDX 0.035) live ONLY in core.pricing; a first S13
    draft charged maker fills the taker rate (a 4x overcharge that alone ate a 1c edge). We
    catch two shapes: (A) a constant/kwarg whose identifier contains fee/rate/coeff as an
    underscore-delimited token bound to a banned literal, and (B) a banned literal passed
    positionally into a fee_per_contract() call. Comment lines are skipped (like the rho
    rule); 0.0035 (longshot's maker-fee modeling haircut) is NOT a schedule rate and
    deliberately does not match."""
    if _file_excluded(path) or _rel(path) == SANCTIONED["fee_rate"]:
        return None
    # (A) name-bound: <fee|rate|coeff identifier> [: type] = 0.07 / 0.0175 / 0.035
    # fee/rate/coeff must be a whole underscore-delimited token segment (or the entire
    # identifier), NOT a raw substring: segments allow digits so SP500_NDX_FEE_RATE still
    # fires, but benign words that merely contain the substring (accurate, coffee, separate,
    # generate, moderate, corporate) do not (verifier catch: substring FP on those names).
    pat_a = re.compile(
        r'(?i)\b(?:[a-z0-9]+_)*(?:fee|rate|coeff)(?:_[a-z0-9]+)*\s*(?::\s*[a-z_.\[\]]+\s*)?=\s*'
        r'0?\.(?:07|0175|035)\b'
    )
    # (B) positional banned literal into a fee call: fee_per_contract(x, 0.07)
    pat_b = re.compile(r'fee_per_contract\s*\([^)]*[,(]\s*0?\.(?:07|0175|035)\b')
    hits = [(i, ln) for i, ln in _scan_lines(text)
            if not ln.lstrip().startswith("#") and (pat_a.search(ln) or pat_b.search(ln))]
    return _fmt(path, hits,
                "hand-rolled Kalshi fee rate — lesson L5 (a 4x maker/taker overcharge sank an "
                "S13 draft): import core.pricing.TAKER_FEE_RATE / MAKER_FEE_RATE / "
                "SP500_NDX_FEE_RATE, never a literal") if hits else None


def inv_no_http_server(path: Path, text: str) -> Optional[str]:
    """#6 No FastAPI / HTTP server framework."""
    if _file_excluded(path):
        return None
    pat = re.compile(
        r'^\s*(?:from|import)\s+'
        r'(fastapi|flask|starlette|aiohttp\.web|tornado|bottle|sanic|quart|uvicorn|gunicorn)\b'
    )
    hits = [(i, ln) for i, ln in _scan_lines(text) if pat.search(ln)]
    return _fmt(path, hits, "HTTP server import — Hard Rule #6 forbids FastAPI/HTTP servers") if hits else None


def inv_order_endpoints_confined(path: Path, text: str) -> Optional[str]:
    """Execution-lane invariant (2026-07-12 Stop-rules amendment). Authenticated/order
    endpoint markers may exist ONLY in execution/kalshi_client.py (unbuilt until a strategy
    nears live graduation). Everything else — collectors, probes, the paper tier — is
    read-only public REST by construction. Catches: order-verb method names, the
    portfolio/orders REST path, and Kalshi auth-signing header names. Comment lines skipped
    (matching the fee-rate rule's convention). Two documented exemptions besides the client:
    scripts/kalshi_sign.py — the KB's OFFLINE signing-scheme repro (kb/kalshi-api/
    01-auth-and-signing.md): throwaway key, no network, knowledge not action; and
    collection/ws_depth.py — the READ-ONLY authenticated WS orderbook_delta collector
    (Ryan opened the WS build gate 2026-07-21, GOAL.md amendment; lesson L145). Kalshi
    requires the signed handshake even for market data, so that file may carry the auth
    headers — but the order-verb half of this rule still applies to it in full.
    Two further FULL exemptions (2026-07-23, closes issue #157, Ryan-approved), mirroring
    scripts/kalshi_sign.py rather than the partial ws_depth.py carve-out — these are test
    files whose entire job is asserting the invariant, not production code that could grow
    an order path by accident: tests/test_ws_depth.py (asserts against fake
    KALSHI-ACCESS-* header literals — offline unit test, no network) and
    tests/test_polymarket_us_live.py (its own test_module_has_no_order_verbs asserts
    "place_order" etc. are ABSENT from the collector source, so the forbidden-verb
    strings appear here only inside a negative-assertion tuple, never as a call).
    Root cause of the original break: PR #153 exempted the two source files but not
    their tests, exactly the collision lesson L145 flagged as a risk before that merge."""
    if _file_excluded(path) or _rel(path) in (SANCTIONED["order_endpoints"],
                                              "scripts/kalshi_sign.py",
                                              "tests/test_ws_depth.py",
                                              "tests/test_polymarket_us_live.py"):
        return None
    if _rel(path) == "collection/ws_depth.py":
        # L145 sanction covers AUTH HEADERS only — an order verb here must still fire.
        pat_orders = re.compile(
            r'(?i)\b(?:place_order|create_order|cancel_order|amend_order'
            r'|batch_create_orders)\b|portfolio/orders')
        hits = [(i, ln) for i, ln in _scan_lines(text)
                if not ln.lstrip().startswith("#") and pat_orders.search(ln)]
        return _fmt(path, hits,
                    "order verb in collection/ws_depth.py — its L145 sanction covers "
                    "read-only auth headers ONLY; order paths stay confined to "
                    "execution/kalshi_client.py") if hits else None
    pat = re.compile(
        r'(?i)\b(?:place_order|create_order|cancel_order|amend_order|batch_create_orders)\b'
        r'|portfolio/orders'
        r'|KALSHI-ACCESS-(?:KEY|SIGNATURE|TIMESTAMP)'
    )
    hits = [(i, ln) for i, ln in _scan_lines(text)
            if not ln.lstrip().startswith("#") and pat.search(ln)]
    return _fmt(path, hits,
                "order/auth endpoint marker outside execution/kalshi_client.py — the "
                "2026-07-12 Stop-rules amendment confines authenticated order paths to that "
                "single sanctioned file; paper tier and collectors are read-only public REST"
                ) if hits else None


def inv_risk_caps_sanctioned(path: Path, text: str) -> Optional[str]:
    """Execution-lane invariant (2026-07-12). Risk-cap constants (MAX_CONTRACTS_PER_ORDER /
    MAX_OPEN_NOTIONAL_DOLLARS / MAX_DAILY_ORDERS) are bound ONLY in execution/limits.py —
    the single site a live tier may import caps from, and the single site Ryan reviews when
    a cap changes. A second binding elsewhere is how a cap silently drifts."""
    if _file_excluded(path) or _rel(path) == SANCTIONED["risk_caps"]:
        return None
    pat = re.compile(
        r'\bMAX_(?:CONTRACTS_PER_ORDER|OPEN_NOTIONAL_DOLLARS|DAILY_ORDERS)\s*(?::\s*[A-Za-z_.\[\]]+\s*)?='
        r'(?!=)'
    )
    hits = [(i, ln) for i, ln in _scan_lines(text)
            if not ln.lstrip().startswith("#") and pat.search(ln)]
    return _fmt(path, hits,
                "risk-cap constant bound outside execution/limits.py — caps live in the one "
                "sanctioned site (2026-07-12 execution-lane amendment); import them, never "
                "rebind them") if hits else None


# ─── Raw datetime.fromisoformat RATCHET (L136/L150: GATING, allowlisted) ─────
#
# Python 3.9's `datetime.fromisoformat` REJECTS two timestamp shapes Kalshi and Polymarket
# emit constantly: a short (1-2 digit) fractional second (`...04.7Z`) and a bare trailing `Z`
# (L136). `core.timeutil.parse_iso_utc` normalizes both (and 9-digit nanosecond fractions)
# before delegating to the stdlib, and is the ONE sanctioned parse path.
#
# L150 proved this is not theoretical: a full census of committed tape found 38.27% of all ISO
# timestamp values (638,730 / 1,669,146) would crash a strict 3.9 consumer, with 0 genuinely
# corrupt values — every one of them parses under `parse_iso_utc`.
#
# Why a STATIC ratchet and not a test: `pyproject.toml` declares `requires-python = ">=3.9"`,
# but CI/this sandbox runs 3.11, where every hazardous shape parses FINE. A unit test therefore
# CANNOT see this hazard — the suite is green on the permissive interpreter no matter how many
# raw call sites exist. Only a source-level assert closes it.
#
# RATCHET semantics (the pins below may only ever SHRINK):
#   * a file NOT listed here (and not sanctioned/excluded) with >=1 raw call  -> FAIL. This is
#     the whole point: a NEW raw call site is blocked at the hook / on --full.
#   * a listed file whose count EXCEEDS its pin                               -> FAIL (debt grew).
#   * a listed file at or below its pin                                       -> pass silently,
#     so a migration that removes call sites is always allowed (lower the pin when you do).
# Never raise a pin to make this green; delete the call site instead.
#
# The 33 files / 39 sites pinned below are the LEGACY debt measured on 2026-07-24 with the
# exact regex this check uses (`_DATETIME_FROMISOFORMAT_RE`, shared with the L141 advisory
# further down, so pins and detector agree by construction). MIGRATING those sites is
# deliberately NOT done here: L150 records that it is behaviour-sensitive per site (tz-aware vs
# naive return values differ, and some call sites compare against naive datetimes), so it stays
# L138/L141 scope. This ratchet only guarantees the debt never grows while that work is pending.
# `date.fromisoformat(` is NOT matched and must never be: a bare `YYYY-MM-DD` day token has no
# fractional field and no `Z`, so it carries none of the 3.9 hazard.
LEGACY_RAW_FROMISOFORMAT_SITES: Dict[str, int] = {
    "collection/burst_capture.py":                      1,
    "collection/crypto_hourly.py":                      2,
    "collection/odds_api.py":                           1,
    "collection/polymarket_pairs.py":                   1,
    "collection/sports_history.py":                     3,
    "scripts/longshot_fade_probe.py":                   1,
    "scripts/probe_ladder_coherence.py":                1,
    "scripts/q24_sports_longshot_maker_fillsim.py":     1,
    "scripts/q25_depth_tape_anatomy.py":                1,
    "scripts/q26_ofi_depth_imbalance_probe.py":         1,
    "scripts/q27_favorite_underpricing_fillsim.py":     1,
    "scripts/q36_kxtempnych_settlement_basis_probe.py": 1,
    "scripts/q37_weather_summer_makerno_probe.py":      1,
    "scripts/q42_crossvenue_funding_join.py":           1,
    "scripts/q43_perp_binary_consistency_probe.py":     1,
    "scripts/s13_maker_fillsim.py":                     1,
    "scripts/s14_ladder_fillsim.py":                    1,
    "scripts/s14_queue_fillsim.py":                     1,
    "scripts/s19_wing_fade_fillsim.py":                 1,
    "scripts/s20_ladder_overround_anatomy.py":          1,
    "scripts/s6_maker_firstcut.py":                     1,
    "scripts/s8_basis_probe.py":                        1,
    "scripts/s9_leadlag_probe.py":                      2,
    "scripts/seed3_listing_age_anatomy.py":             1,
    "scripts/seed5_funding_prior_probe.py":             1,
    "scripts/tape_gap_monitor.py":                      1,
    "scripts/weather_fee_schedule_probe.py":            1,
    "scripts/weather_rehab_s5.py":                      3,
    "tests/test_q27_favorite_underpricing_fillsim.py":  1,
    "tests/test_q30_draw_aversion_maker_probe.py":      1,
    "tests/test_q37_weather_summer_makerno_probe.py":   1,
    "tests/test_seed5_funding_prior_probe.py":          1,
    "tests/test_tape_timestamp_parseability_audit.py":  1,
}


def inv_no_raw_datetime_fromisoformat(path: Path, text: str) -> Optional[str]:
    """L136/L150 GATING ratchet: no NEW raw `datetime.fromisoformat` call site, and no growth of
    the legacy ones. Route every ISO parse through `core.timeutil.parse_iso_utc` — Python 3.9
    (the floor `pyproject.toml` declares) rejects the bare-`Z` and short-fraction shapes that
    make up 38.27% of committed tape timestamps (L150), while CI runs 3.11 where they all parse,
    so no unit test can ever catch a new raw site. Only the datetime flavour is matched;
    `date.fromisoformat(` (day tokens) is harmless and deliberately not flagged. The sanctioned
    site `core/timeutil.py` calls the stdlib parser legitimately, AFTER normalizing the
    fractional field. Comment lines are skipped (same convention as the rho/fee rules). See the
    banner above LEGACY_RAW_FROMISOFORMAT_SITES for the ratchet rules."""
    if _file_excluded(path) or _rel(path) == SANCTIONED["iso_parse"]:
        return None
    hits = [(i, ln) for i, ln in _scan_lines(text)
            if not ln.lstrip().startswith("#") and _DATETIME_FROMISOFORMAT_RE.search(ln)]
    if not hits:
        return None
    pin = LEGACY_RAW_FROMISOFORMAT_SITES.get(_rel(path))
    if pin is not None and len(hits) <= pin:
        return None
    detail = (f"NEW raw datetime.fromisoformat call site"
              if pin is None else
              f"legacy raw datetime.fromisoformat count GREW: {len(hits)} > pinned {pin}")
    return _fmt(path, hits,
                f"{detail} — lessons L136/L150: use core.timeutil.parse_iso_utc; Python 3.9 "
                f"(the declared floor) rejects bare-`Z`/short-fraction timestamps that are "
                f"38.27% of committed tape, and CI runs 3.11 where they all parse, so the test "
                f"suite is structurally blind to this — the pins in "
                f"LEGACY_RAW_FROMISOFORMAT_SITES may only shrink, never rise")


STATIC_INVARIANTS: List[Tuple[str, Callable[[Path, str], Optional[str]]]] = [
    ("no_gefs", inv_no_gefs),
    ("no_bare_pstdev", inv_no_bare_pstdev),
    ("no_pstdev_import", inv_no_pstdev_import),
    ("no_yes_ask_arithmetic", inv_no_yes_ask_arithmetic),
    ("no_static_rho_point_four", inv_no_static_rho_point_four),
    ("no_handrolled_fee_rate", inv_no_handrolled_fee_rate),
    ("no_http_server", inv_no_http_server),
    ("order_endpoints_confined", inv_order_endpoints_confined),
    ("risk_caps_sanctioned", inv_risk_caps_sanctioned),
    ("no_raw_datetime_fromisoformat", inv_no_raw_datetime_fromisoformat),
]


# ─── DB invariants (schema-discovering — the project's DB schema is not frozen yet) ──

def _tables(con: sqlite3.Connection) -> List[str]:
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def _columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def db_inv_price_source_tag(con: sqlite3.Connection) -> Optional[str]:
    """trust-default: any `price_source_tag` column holds only the valid enum (untagged=NULL
    is caught separately by #4 when a pnl is present)."""
    bad_tables = []
    enum = ",".join(f"'{t}'" for t in VALID_SOURCE_TAGS)
    for t in _tables(con):
        if "price_source_tag" not in _columns(con, t):
            continue
        n = con.execute(
            f'SELECT COUNT(*) FROM "{t}" WHERE price_source_tag IS NOT NULL '
            f'AND price_source_tag NOT IN ({enum})'
        ).fetchone()[0]
        if n:
            bad_tables.append(f"{t}({n})")
    return f"price_source_tag: invalid tags in {', '.join(bad_tables)}" if bad_tables else None


def db_inv_pnl_requires_tag(con: sqlite3.Connection) -> Optional[str]:
    """#4 No P&L number without a valid price_source_tag. Any table carrying a `pnl` column
    must carry `price_source_tag`, and every non-NULL pnl row must have a valid tag."""
    enum = ",".join(f"'{t}'" for t in VALID_SOURCE_TAGS)
    problems = []
    for t in _tables(con):
        cols = _columns(con, t)
        if "pnl" not in cols:
            continue
        if "price_source_tag" not in cols:
            problems.append(f"{t}: has pnl but no price_source_tag column (#4)")
            continue
        n = con.execute(
            f'SELECT COUNT(*) FROM "{t}" WHERE pnl IS NOT NULL '
            f'AND (price_source_tag IS NULL OR price_source_tag NOT IN ({enum}))'
        ).fetchone()[0]
        if n:
            problems.append(f"{t}: {n} pnl rows with missing/invalid price_source_tag (#4)")
    return "; ".join(problems) if problems else None


def db_inv_probability_in_range(con: sqlite3.Connection) -> Optional[str]:
    """Any `fair_probability` / `normalized_ask` column stays in [0, 1]."""
    problems = []
    for t in _tables(con):
        for col in ("fair_probability", "normalized_ask"):
            if col not in _columns(con, t):
                continue
            n = con.execute(
                f'SELECT COUNT(*) FROM "{t}" WHERE "{col}" < 0 OR "{col}" > 1'
            ).fetchone()[0]
            if n:
                problems.append(f"{t}.{col}: {n} rows out of [0,1]")
    return "; ".join(problems) if problems else None


DB_INVARIANTS: List[Tuple[str, Callable[[sqlite3.Connection], Optional[str]]]] = [
    ("price_source_tag", db_inv_price_source_tag),
    ("pnl_requires_tag", db_inv_pnl_requires_tag),
    ("probability_in_range", db_inv_probability_in_range),
]


# ─── Scanners ─────────────────────────────────────────────────────────────────

def scan_text(path: Path, text: str) -> List[str]:
    out = []
    for name, fn in STATIC_INVARIANTS:
        msg = fn(path, text)
        if msg:
            out.append(f"[{name}] {msg}")
    return out


def scan_tree() -> List[str]:
    out = []
    for path in _iter_source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        out.extend(scan_text(path, text))
    return out


def scan_db(db_path: Path) -> List[str]:
    if not db_path.exists():
        return [f"db not found: {db_path}"]
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        out = []
        for name, fn in DB_INVARIANTS:
            try:
                msg = fn(con)
            except sqlite3.OperationalError:
                msg = None  # table/column gone — pre-data, not a violation
            if msg:
                out.append(f"[{name}] {msg}")
        return out
    finally:
        con.close()


# ─── Stranded-tape warning (L17: non-gating, offline-safe advisory) ──────────────

def _git_tape_refs() -> List[str]:
    """Local-clone knowledge of `tape/hourly-*` fallback branches (both origin-tracking and
    local heads). The hourly collector's push to main fails intermittently and strands tape on
    these refs (lesson L17). This is a best-effort, fully offline-safe probe: ANY failure
    (missing git, nonzero exit, timeout, exception) yields [] so it can never poison the gate."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "for-each-ref",
             "refs/remotes/origin/tape/hourly-*", "refs/heads/tape/hourly-*",
             "--format=%(refname:short)"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return []
    if out.returncode != 0:
        return []
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def stranded_tape_warning(refs: List[str]) -> Optional[str]:
    """A non-gating advisory message when local tape/hourly-* refs exist, else None. Pure."""
    if not refs:
        return None
    n = len(refs)
    examples = ", ".join(refs[:3]) + (", ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} local tape/hourly-* ref(s) known to this clone "
        f"(e.g. {examples}). These are LOCAL refs as of the last fetch — they may carry tape "
        f"lines `main` is missing. This is advisory only and does NOT affect the exit code; "
        f"run LOOP-QUEUE step 0b (git fetch origin, then the union-append line-set sweep) to "
        f"reconcile them before trusting the canonical tape."
    )


# ─── Tape dir-shape warning (L25: non-gating, offline-safe advisory) ─────────

def _tape_dir_shape_issues(tape_root: Path = ROOT / "tape") -> List[str]:
    """A `dt=<date>` entry under any `tape/<family>/` dir must be the canonical .jsonl
    file, never a directory (lesson L25: the 2026-07-08 main-rewind briefly ran collector
    code that wrote raw per-market blobs into a `dt=<date>/` directory instead of appending
    the canonical `dt=<date>.jsonl` line format — a naive day-count gate that only checks
    path existence would miscount such a directory as a valid day). Best-effort/offline:
    ANY failure (missing tape/, permission error, exception) yields [] so it can never
    poison the gate. Returns `family/dt=<date>` labels, sorted."""
    try:
        if not tape_root.is_dir():
            return []
        issues = []
        for family_dir in sorted(p for p in tape_root.iterdir() if p.is_dir()):
            for entry in sorted(family_dir.glob("dt=*")):
                if entry.is_dir():
                    issues.append(f"{family_dir.name}/{entry.name}")
        return issues
    except Exception:
        return []


def tape_dir_shape_warning(issues: List[str]) -> Optional[str]:
    """A non-gating advisory message when tape/<family>/dt=<date> paths are directories
    instead of the canonical .jsonl file, else None. Pure."""
    if not issues:
        return None
    n = len(issues)
    examples = ", ".join(issues[:3]) + (", ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} tape/<family>/dt=<date> path(s) are DIRECTORIES, not "
        f"the canonical .jsonl file (e.g. {examples}). A day-count gate (e.g. LOOP-QUEUE.md "
        f"Q7/Q13) that only checks path existence would miscount these as valid days — verify "
        f"file shape before trusting a day-count. See kb/lessons/00-lessons.md L25."
    )


# ─── Orphaned dir-shape GC classification (L109: non-gating, offline-safe advisory) ──

def _tape_dir_shape_orphan_classification(tape_root: Path = ROOT / "tape") -> List[Tuple[str, str]]:
    """For each directory-shaped `dt=<date>` entry (L25), classify it for GC dispatch —
    L25's assert stops at "this is the wrong shape" and never says what to DO about one
    (lesson L109: 3 such directories sat in `tape/sports_pairs/` for 9+ days after L25's
    forward-collection fix, undetected because no check distinguished "safe to delete" from
    "needs a human"). Two classes, both best-effort/offline (any exception on one entry is
    swallowed and that entry is skipped, never poisoning the others):

    - "superseded": a canonical `dt=<date>.jsonl` file for the SAME date already exists
      alongside the directory -> the directory is pure post-fix debris, safe to delete.
    - "unrecoverable": no canonical file for that date exists, and the family has at least
      one canonical `.jsonl` day STRICTLY AFTER it -> forward collection has already moved
      on, so this day will never self-heal via normal cadence; it is a permanently missing
      day, not a pending one, and needs a human decision (backfill or accept the gap).

    A directory whose date is >= the family's latest canonical day is deliberately left
    unclassified (returned as neither) — collection may still be catching up to it, so
    flagging it for GC/backfill would be premature. Returns sorted (label, classification)
    pairs."""
    out: List[Tuple[str, str]] = []
    try:
        if not tape_root.is_dir():
            return out
        for family_dir in sorted(p for p in tape_root.iterdir() if p.is_dir()):
            try:
                canonical_days = sorted(
                    date.fromisoformat(p.name[len("dt="):-len(".jsonl")])
                    for p in family_dir.glob("dt=*.jsonl")
                    if p.is_file()
                )
            except Exception:
                canonical_days = []
            latest_canonical = canonical_days[-1] if canonical_days else None
            canonical_set = set(canonical_days)
            for entry in sorted(family_dir.glob("dt=*")):
                if not entry.is_dir():
                    continue
                label = f"{family_dir.name}/{entry.name}"
                try:
                    entry_date = date.fromisoformat(entry.name[len("dt="):])
                except Exception:
                    continue
                if entry_date in canonical_set:
                    out.append((label, "superseded"))
                elif latest_canonical is not None and entry_date < latest_canonical:
                    out.append((label, "unrecoverable"))
                # else: at/after the family's latest day — collection may still be
                # catching up, deliberately left unclassified (L109 scope).
        return out
    except Exception:
        return []


def tape_dir_shape_orphan_warning(classified: List[Tuple[str, str]]) -> Optional[str]:
    """A non-gating advisory summarizing GC-actionable directory-shaped `dt=<date>` orphans,
    else None. Pure."""
    if not classified:
        return None
    superseded = [label for label, cls in classified if cls == "superseded"]
    unrecoverable = [label for label, cls in classified if cls == "unrecoverable"]
    parts = []
    if superseded:
        ex = ", ".join(superseded[:3]) + (", ..." if len(superseded) > 3 else "")
        parts.append(f"{len(superseded)} SUPERSEDED (safe to delete: canonical .jsonl already exists — e.g. {ex})")
    if unrecoverable:
        ex = ", ".join(unrecoverable[:3]) + (", ..." if len(unrecoverable) > 3 else "")
        parts.append(f"{len(unrecoverable)} UNRECOVERABLE (collection has moved past this day, permanently missing — e.g. {ex})")
    if not parts:
        return None
    return (
        "warning (non-gating): GC dispatch for directory-shaped tape/<family>/dt=<date> "
        "orphans (L25 flags the wrong shape; this classifies what to do about it): "
        + "; ".join(parts) + ". See kb/lessons/00-lessons.md L109."
    )


# ─── Daily-cadence family gap warning (L74: non-gating, offline-safe advisory) ────

# The tape families `collection/hourly_pass.py` gates to a single fixed `now.hour == N` UTC
# window (anomaly_sweep -> tape/anomalies/, econ_prints, polymarket_cpi_pairs at hour 9;
# weather_actuals at hour 12, L126) with no retry/backfill — one bad hour costs a full
# calendar day of coverage, and unlike the always-hourly families a missed day leaves no
# other capture to catch it (L74). `weather_actuals` added 2026-07-21 (L126) after a live
# 2-day hole (2026-07-19, 2026-07-20) was found in committed tape: the live collector's
# effective cron phase (post-VPS-death, ~hours {01,04,07,10,13,16,19,22}) never lands on
# hour 12, so this exact-hour leg was silently starved by the same mechanism L74/L123
# already documented for other families — but this family itself was never added to this
# list, so the one tool built to catch it (`daily_family_gap_warning`) could not see it.
# `settlement_ledger` added 2026-07-24 (L144, closing L123's structural residue): it is
# gated at `SETTLEMENT_LEDGER_UTC_HOUR=10` (`collection/hourly_pass.py`) and writes committed
# `tape/settlement_ledger/`, but the every-3h live cron never lands on hour 10 (L123) so the
# family froze at its `dt=2026-07-17` build day — the direct data-adequacy blocker on Q36 —
# and was never registered here even after its twin freeze was root-caused. The unregistered-
# leg meta-guard below now trips the moment a future single-hour committed leg forgets this.
DAILY_CADENCE_FAMILIES = ("anomalies", "econ_prints", "polymarket_cpi_pairs", "weather_actuals",
                          "settlement_ledger")


def _daily_family_gap_issues(tape_root: Path = ROOT / "tape",
                              families: Tuple[str, ...] = DAILY_CADENCE_FAMILIES) -> List[str]:
    """Missing calendar days, per daily-cadence family, between that family's earliest and
    latest committed `dt=<date>.jsonl` file (lesson L74). Best-effort/offline: ANY failure
    (missing tape/, unparseable filename, permission error, exception) is swallowed per-family
    so it can never poison the gate. A family with 0 or 1 files has no interior to gap-check
    and is silently skipped. Returns `family/dt=<date>` labels for each missing day, sorted."""
    issues: List[str] = []
    if not tape_root.is_dir():
        return issues
    for family in families:
        family_dir = tape_root / family
        try:
            if not family_dir.is_dir():
                continue
            days = sorted(
                date.fromisoformat(p.name[len("dt="):-len(".jsonl")])
                for p in family_dir.glob("dt=*.jsonl")
                if p.is_file()
            )
            if len(days) < 2:
                continue
            present = set(days)
            d = days[0]
            while d < days[-1]:
                if d not in present:
                    issues.append(f"{family}/dt={d.isoformat()}")
                d += timedelta(days=1)
        except Exception:
            continue
    return issues


def daily_family_gap_warning(issues: List[str]) -> Optional[str]:
    """A non-gating advisory message when a daily-cadence family is missing a calendar day
    between its earliest and latest committed tape file, else None. Pure."""
    if not issues:
        return None
    n = len(issues)
    examples = ", ".join(issues[:3]) + (", ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} daily-cadence tape day(s) missing (e.g. {examples}). "
        f"These families ({', '.join(DAILY_CADENCE_FAMILIES)}) capture only during a single "
        f"UTC hour with no retry/backfill, so one bad hour blacks out a full day with nothing "
        f"else to catch it. See kb/lessons/00-lessons.md L74."
    )


# ─── Unregistered single-hour committed leg meta-guard (L144: non-gating, offline-safe) ──

# `collection/hourly_pass.py` runs several legs ONCE per UTC day, gated on exact single-hour
# equality (`if ts.hour == <NAME>_UTC_HOUR:`). Such a leg has no catch-up: if the scheduler
# never lands on hour N, the family it writes silently FREEZES with no error (L123/L124 for
# settlement_ledger, L126 for weather_actuals — both cost real committed-tape holes). The one
# tool built to surface that freeze, `daily_family_gap_warning`, can only see a family listed
# in DAILY_CADENCE_FAMILIES. Twice now (weather_actuals, then settlement_ledger) a real leg
# was added and simply never registered, so the freeze stayed invisible. This meta-guard
# closes the STRUCTURAL half L123 left open: it parses hourly_pass.py, finds every single-hour
# leg, resolves the committed tape family/families it writes, and asserts each is monitored —
# so the NEXT unregistered leg trips CI instead of freezing in silence. (The trailing-edge
# freeze DETECTION half is already handled at runtime by scripts/tape_gap_monitor.py, where
# settlement_ledger was registered by L124 — this guard is deliberately structural, not
# wall-clock, so it stays deterministic and offline.) The plural `*_UTC_HOURS` set-membership
# gate (universe_sweep, fires 4x/day on {0,6,12,18}) is NOT a single-hour leg and is excluded.

# Maps each single-hour `*_UTC_HOUR` constant in hourly_pass.py to the committed tape
# family/families it gates. ECON_PRINTS_UTC_HOUR gates two (econ_prints AND the polymarket_cpi
# leg reused at the same hour). Every family here must be in DAILY_CADENCE_FAMILIES.
SINGLE_HOUR_LEG_FAMILIES: Dict[str, Tuple[str, ...]] = {
    "ANOMALY_SWEEP_UTC_HOUR": ("anomalies",),
    "ECON_PRINTS_UTC_HOUR": ("econ_prints", "polymarket_cpi_pairs"),
    "WEATHER_ACTUALS_UTC_HOUR": ("weather_actuals",),
    "SETTLEMENT_LEDGER_UTC_HOUR": ("settlement_ledger",),
}
# Single-hour legs that DELIBERATELY write no committed tape/<family>, with the documented
# reason each is exempt from cadence monitoring (nothing to gap-check).
SINGLE_HOUR_LEG_EXEMPT: Dict[str, str] = {
    "FORECAST_COLLECTOR_UTC_HOUR": ("writes gitignored data/forecast_tape/, never a committed "
                                    "tape/ family (L123/L124) — nothing to gap-check"),
}

_TS_HOUR_EQ_RE = re.compile(r"ts\.hour\s*==\s*([A-Za-z_][A-Za-z0-9_]*)")


def _unregistered_single_hour_leg_issues(
        hourly_pass_path: Path = ROOT / "collection" / "hourly_pass.py",
        monitored: Tuple[str, ...] = DAILY_CADENCE_FAMILIES,
        known: Optional[Dict[str, Tuple[str, ...]]] = None,
        exempt: Optional[Dict[str, str]] = None,
        source: Optional[str] = None) -> List[str]:
    """Every single-hour committed leg (`if ts.hour == <NAME>_UTC_HOUR:`) in hourly_pass.py
    whose resolved committed tape family is NOT in `monitored` and NOT documented-exempt
    (lesson L144). Best-effort/offline: ANY failure (missing file, read error, exception) is
    swallowed and returns [] so it can never poison the gate. `source`/`known`/`exempt` are
    injectable for offline testing; each defaults to the real file / real maps. A constant the
    guard does NOT recognize is SURFACED (not silently passed) — the point is that a future
    `*_UTC_HOUR` leg added without registration trips here. Returns sorted issue labels."""
    known = SINGLE_HOUR_LEG_FAMILIES if known is None else known
    exempt = SINGLE_HOUR_LEG_EXEMPT if exempt is None else exempt
    issues: List[str] = []
    try:
        if source is None:
            source = hourly_pass_path.read_text(encoding="utf-8")
        names = {n for n in _TS_HOUR_EQ_RE.findall(source) if n.endswith("_UTC_HOUR")}
        for name in names:
            if name in exempt:
                continue
            if name in known:
                for fam in known[name]:
                    if fam not in monitored:
                        issues.append(
                            f"{name} -> tape/{fam} (single-hour committed leg not in "
                            f"DAILY_CADENCE_FAMILIES)")
            else:
                issues.append(
                    f"{name} (unrecognized single-hour leg; resolve its committed tape family "
                    f"and add to DAILY_CADENCE_FAMILIES + SINGLE_HOUR_LEG_FAMILIES, or exempt it)")
    except Exception:
        return []
    return sorted(issues)


def unregistered_single_hour_leg_warning(issues: List[str]) -> Optional[str]:
    """A non-gating advisory message when a single-hour committed collector leg in
    collection/hourly_pass.py is not registered for daily-cadence monitoring, else None. Pure."""
    if not issues:
        return None
    n = len(issues)
    examples = "; ".join(issues[:3]) + ("; ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} single-hour committed collector leg(s) in "
        f"collection/hourly_pass.py are not registered for daily-cadence monitoring "
        f"(e.g. {examples}). A once-per-UTC-day `if ts.hour == N` leg that writes a committed "
        f"tape/<family> silently FREEZES if the scheduler never lands on hour N (L123/L124/"
        f"L126), and only DAILY_CADENCE_FAMILIES membership lets daily_family_gap_warning see "
        f"it. Register the family (or add a documented SINGLE_HOUR_LEG_EXEMPT reason). "
        f"See kb/lessons/00-lessons.md L144."
    )


# ─── Raw datetime.fromisoformat advisory (L138 residue: non-gating, offline-safe) ──

_DATETIME_FROMISOFORMAT_RE = re.compile(r"\bdatetime\.fromisoformat\s*\(")
_ISO_PARSE_SANCTIONED = ("core/timeutil.py",)  # home of core.timeutil.parse_iso_utc (L138)


def _raw_datetime_fromisoformat_sites(root: Path = ROOT) -> List[str]:
    """Production call sites of `datetime.fromisoformat(` outside the sanctioned
    core/timeutil.py (L136/L138). Python 3.9's datetime.fromisoformat rejects a short (1-2
    digit) fractional second and a bare `Z`; core.timeutil.parse_iso_utc normalizes those
    first, so every other call site is a latent 3.9 crash on a Kalshi ts like `...04.7Z`.
    `date.fromisoformat` (date-only) is NOT flagged (no fractional/tz hazard). tests/ construct
    fixtures, not production parse paths. Best-effort/offline: any exception skips a file and
    can never poison the gate. Returns sorted `path:line` labels."""
    out: List[str] = []
    try:
        for p in _iter_source_files(root, exts=(".py",)):
            rel = str(p.resolve().relative_to(root.resolve())).replace("\\", "/")
            if rel in _ISO_PARSE_SANCTIONED or rel.split("/", 1)[0] == "tests":
                continue
            try:
                lines = p.read_text().splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    continue
                if _DATETIME_FROMISOFORMAT_RE.search(line):
                    out.append(f"{rel}:{i}")
        return sorted(out)
    except Exception:
        return []


def raw_datetime_fromisoformat_warning(sites: List[str]) -> Optional[str]:
    """Non-gating advisory when production code calls datetime.fromisoformat directly instead
    of core.timeutil.parse_iso_utc, else None. Pure."""
    if not sites:
        return None
    n = len(sites)
    examples = ", ".join(sites[:3]) + (", ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} production call site(s) use `datetime.fromisoformat(` "
        f"directly instead of `core.timeutil.parse_iso_utc` (e.g. {examples}). On Python 3.9 a "
        f"Kalshi timestamp with a short fractional second or bare `Z` (e.g. `...04.7Z`) crashes "
        f"there (L136/L138); parse_iso_utc normalizes it first. Advisory only — does NOT affect "
        f"the exit code. See kb/lessons/00-lessons.md L138."
    )


_LESSON_ID_ROW_RE = re.compile(r"^\|\s*(L\d+)\s*\|")


def _duplicate_lesson_id_issues(
    lessons_path: Path = ROOT / "kb" / "lessons" / "00-lessons.md",
) -> List[str]:
    """Lesson IDs (`L<n>`) that appear on more than one row of kb/lessons/00-lessons.md's
    table (2026-07-24 incident: L130 and L131 were each independently assigned to two
    unrelated lessons by concurrent runs that didn't check the ledger's current max ID before
    picking a number — one silently shadows the other in every future citation). Only the
    table's ID column (`| L<n> |` at line start) is matched; prose mentions of an ID elsewhere
    in a row's own text are not counted. Best-effort/offline: a read failure returns [] and
    can never poison the gate. Returns sorted `L<n>` labels for every ID with >1 row."""
    try:
        lines = lessons_path.read_text().splitlines()
    except Exception:
        return []
    try:
        seen: Dict[str, int] = {}
        for line in lines:
            m = _LESSON_ID_ROW_RE.match(line)
            if m:
                seen[m.group(1)] = seen.get(m.group(1), 0) + 1
        dupes = sorted(
            (lid for lid, n in seen.items() if n > 1),
            key=lambda lid: int(lid[1:]),
        )
        return dupes
    except Exception:
        return []


def duplicate_lesson_id_warning(dupes: List[str]) -> Optional[str]:
    """Non-gating advisory when kb/lessons/00-lessons.md assigns the same lesson ID to more
    than one row, else None. Pure."""
    if not dupes:
        return None
    n = len(dupes)
    examples = ", ".join(dupes[:5]) + (", ..." if n > 5 else "")
    return (
        f"warning (non-gating): {n} lesson ID(s) in kb/lessons/00-lessons.md are assigned to "
        f"more than one row (e.g. {examples}) — a duplicate ID means later citations of that "
        f"number are ambiguous between two unrelated lessons. Give the newer/less-cited row a "
        f"fresh next-free ID instead (grep the ID's own citations first to see which meaning is "
        f"load-bearing); do not renumber a row that is only cited under its current ID. "
        f"Advisory only — does NOT affect the exit code. See kb/lessons/00-lessons.md L147."
    )


# ─── Tape conflict-marker gate (GATING, not advisory) ────────────────────────
#
# Real incident (2026-07-23): tape/econ_prints/dt=2026-07-18.jsonl and
# tape/anomalies/dt=2026-07-18.jsonl were each committed with 3 unresolved git
# merge-conflict-marker lines (`<<<<<<< HEAD` / `=======` / `>>>>>>> <sha> (...)`) —
# invalid JSON silently sitting in the append-only audit trail, undetected until a
# tape-quality audit found them by hand. A conflict marker is never legitimate JSONL
# content and is cheap/unambiguous to detect, so — unlike the advisories above — this
# is a GATING check: it flips scan_tree()'s exit code.

_CONFLICT_MARKER_RE = re.compile(rb"^(<{7}|>{7}|={7}$)")


def _tape_conflict_marker_issues(tape_root: Path = ROOT / "tape") -> List[str]:
    """Committed tape/**/*.jsonl lines that are unresolved git conflict markers (see
    banner above). Best-effort/offline: a per-file read failure just skips that file, never
    poisons the whole scan; a raw-bytes pre-check on the common case (no marker bytes present
    at all) avoids paying the line-split cost on every large tape file. Returns sorted
    `path:line` labels.

    Deliberately left filesystem-scoped (NOT git-tracked-scoped like the sibling invalid-JSON
    gate): a `<<<<<<<`/`=======`/`>>>>>>>` marker only ever arises from a MERGE of tracked
    content, so it cannot appear in an untracked collector-in-flight file the way a torn last
    line can — the wedge that motivated scoping the JSON gate to tracked files simply has no
    analog here, and an fs-wide sweep is strictly the safer (never-miss) posture for this
    unambiguous corruption shape."""
    out: List[str] = []
    if not tape_root.is_dir():
        return out
    try:
        for p in sorted(tape_root.rglob("*.jsonl")):
            try:
                data = p.read_bytes()
            except Exception:
                continue
            if b"<<<<<<<" not in data and b">>>>>>>" not in data and b"=======" not in data:
                continue
            rel = str(p.relative_to(tape_root).as_posix())
            for i, line in enumerate(data.split(b"\n"), 1):
                if _CONFLICT_MARKER_RE.match(line):
                    out.append(f"{rel}:{i}")
        return sorted(out)
    except Exception:
        return []


def tape_conflict_marker_failure(issues: List[str]) -> Optional[str]:
    """GATING failure message when committed tape carries an unresolved conflict-marker
    line, else None. Pure."""
    if not issues:
        return None
    n = len(issues)
    examples = ", ".join(issues[:5]) + (", ..." if n > 5 else "")
    return (
        f"[tape_conflict_marker] {n} unresolved git conflict-marker line(s) in committed "
        f"tape/**/*.jsonl (e.g. {examples}). A conflict marker is never valid JSONL — strip "
        f"the marker line(s) only, never touch the surrounding real capture lines (append-"
        f"only). See kb/lessons/00-lessons.md (2026-07-23 tape-corruption finding)."
    )


# ─── Tape invalid-JSON gate (GATING, not advisory) ───────────────────────────
#
# L142 generalization: a git conflict marker (caught above) is only one shape of the same
# class of bug — a committed tape/**/*.jsonl line that is not valid JSON. A truncated write
# (`{"a": 1,`), an encoding-corrupted byte run, or any stray non-JSON line is equally invalid
# in an append-only audit trail and equally cheap/unambiguous to detect via json.loads. The
# conflict-marker-only gate misses every non-marker corruption; this gate closes that hole.
# Both are GATING (flip scan_tree()'s exit code).
#
# Conflict-marker overlap (design choice, per milestone #5, option (a)): a conflict-marker
# line also fails json.loads. To keep L142's specific diagnostic intact and avoid
# double-reporting, THIS check SKIPS any line already owned by the conflict-marker gate
# (lines starting with `<<<<<<<` / `=======` / `>>>>>>>`), so a conflict marker stays the
# conflict-marker gate's job and this gate reports only OTHER invalid JSON.

_CONFLICT_MARKER_PREFIXES = ("<<<<<<<", "=======", ">>>>>>>")


def _git_tracked_jsonl(tape_root: Path = ROOT / "tape") -> set:
    """Set of resolved Paths of git-TRACKED `.jsonl` files under `tape_root`.

    Scope fix (L142): the invalid-JSON gate must guard the COMMITTED append-only audit trail
    ONLY. Walking the raw working tree also picks up UNTRACKED / in-flight files — a collector
    mid-append leaves a torn last line (no trailing newline yet) in an uncommitted file, and
    failing json.loads on that never-committed line would flip this GATING check to exit 2 and
    wedge the autonomous loop on data that was never part of the audit trail (two untracked
    live-capture files literally appeared mid-run on 2026-07-24, proving this). `git ls-files`
    returns tracked AND staged files — the staged set is exactly the tape about to be committed,
    which we DO want validated — so it is the correct scope.

    Best-effort/offline: ANY failure (not a repo, git missing, non-zero exit, timeout, or any
    exception) returns an EMPTY set so the GATING check simply skips those files — a gating
    check must NEVER flip the exit code because of an environment/git failure (same posture as
    `_daily_family_gap_issues` / `_git_tape_refs`). `ls-files` prints repo-root-relative POSIX
    paths, which are resolved against ROOT."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--", str(tape_root)],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return set()
    if out.returncode != 0:
        return set()
    tracked = set()
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.endswith(".jsonl"):
            try:
                tracked.add((ROOT / line).resolve())
            except Exception:
                continue
    return tracked


def _tape_invalid_jsonl_issues(tape_root: Path = ROOT / "tape",
                               tracked_files: Optional[set] = None) -> List[str]:
    """Committed tape/**/*.jsonl lines that fail json.loads for a reason OTHER than being a
    git conflict marker (those stay the conflict-marker gate's job — see banner). Scope is
    git-TRACKED `*.jsonl` ONLY (never .raw.json / meta / .md orphans under tape/, and never
    UNTRACKED / in-flight files — see `_git_tracked_jsonl` for why an uncommitted torn line
    must not wedge this GATING check). When `tracked_files is None` the tracked set is resolved
    via `_git_tracked_jsonl(tape_root)`; tests inject an explicit set so the scope is testable
    without a real git repo in the fixture. Note there is NO torn-last-line leniency for a
    tracked file — a committed torn line IS real corruption (L142's class) and must still be
    caught; the fix is scope (exclude untracked), not tolerance. Empty/whitespace-only stripped
    lines are legal trailing-newline JSONL and skipped. Best-effort/offline: a per-file READ
    failure just skips that file (transient FS/encoding open error, same posture as
    `_daily_family_gap_issues`), but a successfully-read non-empty line that deterministically
    fails json.loads IS a real gating failure and is recorded. Returns sorted
    `path:line (snippet)` labels."""
    out: List[str] = []
    if not tape_root.is_dir():
        return out
    if tracked_files is None:
        tracked_files = _git_tracked_jsonl(tape_root)
    try:
        for p in sorted(tape_root.rglob("*.jsonl")):
            if p.resolve() not in tracked_files:
                continue  # untracked / in-flight file — not part of the committed audit trail
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                # Transient/odd file-read error (encoding, permissions, race) -> skip this
                # file, never crash the gate.
                continue
            rel = str(p.relative_to(tape_root).as_posix())
            for i, raw_line in enumerate(text.split("\n"), 1):
                line = raw_line.strip()
                if not line:
                    continue  # trailing-newline / blank line is legal JSONL, not an error
                if line.startswith(_CONFLICT_MARKER_PREFIXES):
                    continue  # owned by the conflict-marker gate; do not double-report
                try:
                    json.loads(line)
                except Exception:
                    snippet = line[:40] + ("..." if len(line) > 40 else "")
                    out.append(f"{rel}:{i} ({snippet})")
        return sorted(out)
    except Exception:
        return []


def tape_invalid_jsonl_failure(issues: List[str]) -> Optional[str]:
    """GATING failure message when committed tape carries a non-empty line that fails
    json.loads (and is not a conflict marker), else None. Pure."""
    if not issues:
        return None
    n = len(issues)
    examples = ", ".join(issues[:5]) + (", ..." if n > 5 else "")
    return (
        f"[tape_invalid_jsonl] {n} invalid-JSON line(s) in committed tape/**/*.jsonl "
        f"(e.g. {examples}). Every non-empty line of append-only tape must parse as JSON — a "
        f"truncated/encoding-corrupted/stray line is silent corruption of the audit trail. "
        f"Strip or repair the bad line(s) only, never touch the surrounding real capture "
        f"lines (append-only). See kb/lessons/00-lessons.md L142."
    )


# ─── PreToolUse hook ────────────────────────────────────────────────────────

def _post_edit_content(file_path: Path, old: str, new: str) -> Optional[str]:
    if not file_path.exists():
        return None
    try:
        current = file_path.read_text(encoding="utf-8")
    except Exception:
        return None
    return current.replace(old, new, 1) if old in current else None


def handle_pre_edit_hook() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        return 0
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {}) or {}
    raw = inp.get("file_path") or inp.get("path") or ""
    if not raw:
        return 0
    fp = Path(raw)
    if not fp.is_absolute():
        fp = (ROOT / fp).resolve()
    if not _is_inside_root(fp) or fp.suffix not in (".py", ".sql"):
        return 0

    if tool == "Write":
        text = inp.get("content", "")
    elif tool == "Edit":
        text = _post_edit_content(fp, inp.get("old_string", ""), inp.get("new_string", ""))
        if text is None:
            return 0
    else:
        return 0

    failures = scan_text(fp, text)
    if failures:
        sys.stderr.write("BLOCKED by invariants — Hard Rule violation in prospective edit:\n")
        for f in failures:
            sys.stderr.write(f + "\n")
        sys.stderr.write("\nFix the violation in the proposed content and retry. "
                         "Rationale for each rule lives in CLAUDE.md.\n")
        return 2
    return 0


# ─── CLI ────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="kalshi.headless Hard-Rule invariants")
    p.add_argument("--pre-edit-hook", action="store_true",
                   help="PreToolUse hook mode: read stdin JSON, exit 2 on violation")
    p.add_argument("--full", action="store_true", help="Scan whole tree (default)")
    p.add_argument("--db", type=Path, default=None, help="Run DB invariants against this SQLite")
    args = p.parse_args()

    if args.pre_edit_hook:
        return handle_pre_edit_hook()

    if args.db is not None:
        failures = scan_db(args.db)
    else:
        failures = scan_tree()
        # L17 advisory: surface locally-known stranded tape/hourly-* refs on the whole-tree
        # scan only. Non-gating — printed to stderr, never flips the exit code.
        warning = stranded_tape_warning(_git_tape_refs())
        if warning:
            sys.stderr.write(warning + "\n")
        # L25 advisory: surface any tape/<family>/dt=<date> path that is a directory
        # instead of the canonical .jsonl file. Non-gating — printed to stderr only.
        shape_warning = tape_dir_shape_warning(_tape_dir_shape_issues())
        if shape_warning:
            sys.stderr.write(shape_warning + "\n")
        # L109 advisory: classify directory-shaped dt=<date> orphans for GC dispatch
        # (superseded-by-canonical-file vs permanently-unrecoverable). Non-gating.
        orphan_warning = tape_dir_shape_orphan_warning(_tape_dir_shape_orphan_classification())
        if orphan_warning:
            sys.stderr.write(orphan_warning + "\n")
        # L74 advisory: surface missing calendar days in the single-hour-gated daily-cadence
        # families. Non-gating — printed to stderr only.
        gap_warning = daily_family_gap_warning(_daily_family_gap_issues())
        if gap_warning:
            sys.stderr.write(gap_warning + "\n")
        # L144 advisory: a single-hour committed leg in hourly_pass.py that is not registered
        # in DAILY_CADENCE_FAMILIES (the structural gap that hid the weather_actuals/L126 and
        # settlement_ledger/L123 freezes). Non-gating — stderr only, never flips the exit code.
        leg_warning = unregistered_single_hour_leg_warning(_unregistered_single_hour_leg_issues())
        if leg_warning:
            sys.stderr.write(leg_warning + "\n")
        # L138 advisory: production datetime.fromisoformat sites bypassing core.timeutil
        # .parse_iso_utc (a latent Python-3.9 short-fraction/Z crash). Non-gating.
        iso_warning = raw_datetime_fromisoformat_warning(_raw_datetime_fromisoformat_sites())
        if iso_warning:
            sys.stderr.write(iso_warning + "\n")
        # L147 advisory: kb/lessons/00-lessons.md assigning the same lesson ID to more than
        # one row (2026-07-24 incident: L130/L131 each collided). Non-gating — stderr only.
        dup_lesson_warning = duplicate_lesson_id_warning(_duplicate_lesson_id_issues())
        if dup_lesson_warning:
            sys.stderr.write(dup_lesson_warning + "\n")
        # GATING: an unresolved git conflict marker committed into tape/**/*.jsonl is never
        # valid data (2026-07-23 incident). Unlike the advisories above, this flips the exit
        # code — cheap and unambiguous to catch.
        marker_failure = tape_conflict_marker_failure(_tape_conflict_marker_issues())
        if marker_failure:
            failures.append(marker_failure)
        # GATING (L142 generalization): any OTHER non-empty tape/**/*.jsonl line that fails
        # json.loads (truncated write / encoding corruption / stray non-JSON) is equally
        # silent corruption of the append-only audit trail. Also flips the exit code.
        invalid_jsonl_failure = tape_invalid_jsonl_failure(_tape_invalid_jsonl_issues())
        if invalid_jsonl_failure:
            failures.append(invalid_jsonl_failure)

    if failures:
        sys.stderr.write(f"invariants: {len(failures)} violation(s)\n")
        for f in failures:
            sys.stderr.write(f + "\n")
        return 2
    sys.stdout.write("invariants: all green\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
