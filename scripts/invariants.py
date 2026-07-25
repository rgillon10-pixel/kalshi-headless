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
import ast
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


# ─── Dead collector-leg advisory (L117/L129 recurrence: non-gating, offline-safe) ──
#
# The live data pipe runs TWO staggered collectors (VPS cron :23 UTC, cloud `kalshi-collector`
# :53 UTC — ops/ROUTINES.md). When ONE of them dies the tape keeps growing, every family keeps
# a fresh newest-capture, and nothing in the run protocol notices: the VPS leg died 2026-07-19
# (L117), was declared RECOVERED 2026-07-22 (L129), then died again ~6h later and produced
# nothing for ~61h while three research-loop runs and two edge-hunter runs came and went.
# `scripts/tape_gap_monitor.py` DOES diagnose this correctly (`collector_diagnosis`:
# "vps_dead: 0 passes in window, other collector still producing"), but nothing in the protocol
# runs it, and in a cloud sandbox its only escalation path (an ntfy POST) is a documented no-op
# with no NTFY_TOPIC_URL. `python scripts/invariants.py --full` is the one command every
# autonomous run is REQUIRED to run and read — so the outage is surfaced HERE.
#
# NON-GATING, deliberately and permanently: a dead VPS cron is Ryan/VPS-side and physically
# un-fixable from a cloud sandbox. Gating on it would halt the entire research loop for as long
# as the outage lasts — trading one silent failure for a louder one. It PRINTS, it never flips
# the exit code (same posture as every advisory above).
#
# Single source of truth for the leg signatures: the minute-of-hour bucket ranges
# (`COLLECTOR_MINUTE_BUCKETS`) and the hourly family list (`FAMILY_CONFIG`, kind=="hourly-dual")
# are IMPORTED from scripts/tape_gap_monitor.py, never re-declared here — a second copy would
# drift the moment either is recalibrated (the same duplication trap L100 collapsed out of the
# collectors). Attribution uses `captured_at` minute-of-hour only; git author strings are not a
# durable contract and are never read.

# Thresholds (named, documented — edit here, not in the logic).
# 24h: a scheduled leg firing hourly that has produced NOTHING for a full day has missed ~24
#      consecutive passes — far beyond any restart/jitter/venue-hole explanation (L15's known
#      structural 20-UTC hole is a single hour). This is the "apparently dead", not "hiccuped",
#      boundary.
DEAD_LEG_SILENCE_HOURS = 24.0
# 6h: the survivor test. Another leg capturing within 6h proves the tape pipe, the repo and the
#     venue are all fine, which is what makes a 24h+ silence attributable to ONE leg rather than
#     to a whole-pipe outage (the 2026-07-09 systemic case, which stays AMBIGUOUS here).
DEAD_LEG_ALIVE_HOURS = 6.0
# Bounded I/O: newest N day-files per family (~300MB / ~0.6s across all hourly families on
# 2026-07-25 tape). A leg silent longer than the lookback reports last-seen "unknown" rather
# than a fabricated timestamp — honest, and still correctly flagged dead.
DEAD_LEG_LOOKBACK_DAYS = 10

_CAPTURED_AT_RE = re.compile(rb'"captured_at"\s*:\s*"([^"]{10,40})"')
_TAPE_GAP_MONITOR_PATH = ROOT / "scripts" / "tape_gap_monitor.py"


def _load_tape_gap_monitor(path: Path = _TAPE_GAP_MONITOR_PATH):
    """Import scripts/tape_gap_monitor.py by path (scripts/ is not a package) so this advisory
    reuses its COLLECTOR_MINUTE_BUCKETS / FAMILY_CONFIG rather than copying them. Returns None
    on ANY failure — the advisory then simply does not run, and can never poison the gate."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_inv_tape_gap_monitor", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _monitored_legs() -> Tuple[str, ...]:
    """The SCHEDULED cron legs that can be called dead — DERIVED from
    tape_gap_monitor.COLLECTOR_MINUTE_BUCKETS, never re-listed here, so adding or renaming a
    leg there cannot leave this advisory silently monitoring a stale set. The catch-all
    `other` bucket (ad-hoc smoke runs, plus the secondary weather_books/perp_tape writes
    L120/L127) is excluded by construction: it is not a key of the bucket map, it is
    `collector_bucket`'s fallback. It counts as a survivor signal but is never accused of
    dying — its silence is not evidence of a broken schedule. Falls back to the historical
    pair only if tape_gap_monitor cannot be loaded at all."""
    tgm = _load_tape_gap_monitor()
    try:
        legs = tuple(str(k) for k in tgm.COLLECTOR_MINUTE_BUCKETS if str(k) != "other")
        return legs or ("vps", "cloud")
    except Exception:
        return ("vps", "cloud")


DEAD_LEG_MONITORED = _monitored_legs()


def _leg_schedule_phrase(leg: str) -> str:
    """A non-programmer-readable description of WHEN a leg captures, rendered from the leg's
    own `COLLECTOR_MINUTE_BUCKETS` range. Deliberately derived rather than written in prose:
    a hardcoded ":23 UTC" sentence is a second, silent copy of the collector signature that
    would start lying the moment the buckets are recalibrated — in the exact line a run digest
    is told to quote verbatim. Degrades to a schedule-unknown phrase, never to a stale claim."""
    try:
        bucket = _load_tape_gap_monitor().COLLECTOR_MINUTE_BUCKETS[leg]
        minutes = sorted(int(m) for m in bucket)
        if not minutes:
            return "schedule unknown"
        if len(minutes) == 1:
            return f"captures at minute {minutes[0]} of the hour"
        return f"captures at minutes {minutes[0]}-{minutes[-1]} of the hour"
    except Exception:
        return "schedule unknown"


def _collector_leg_last_seen(tape_root: Path = ROOT / "tape",
                             lookback_days: int = DEAD_LEG_LOOKBACK_DAYS,
                             max_day: Optional[date] = None) -> Dict[str, str]:
    """Newest `captured_at` per collector leg ("vps"/"cloud"/"other"), scanned from committed
    tape only (no network, no git). Legs are bucketed by minute-of-hour using
    tape_gap_monitor.COLLECTOR_MINUTE_BUCKETS; families are its kind=="hourly-dual" entries.
    `max_day` (optional) restricts the scan to `dt=<date>.jsonl` files on or before that day —
    used by tests to pin a FIXED historical slice so a real-tape assertion can never rot as new
    tape lands. Returns {leg: iso-string}; {} when nothing is readable. Best-effort: any
    exception yields {} so it can never poison the gate."""
    out: Dict[str, str] = {}
    try:
        tgm = _load_tape_gap_monitor()
        if tgm is None or not tape_root.is_dir():
            return {}
        families = [f for f, cfg in tgm.FAMILY_CONFIG.items()
                    if cfg.get("kind") == "hourly-dual"]
        for family in families:
            family_dir = tape_root / family
            if not family_dir.is_dir():
                continue
            days = []
            for p in family_dir.glob("dt=*.jsonl"):
                if not p.is_file():
                    continue
                try:
                    d = date.fromisoformat(p.name[len("dt="):-len(".jsonl")])
                except ValueError:
                    continue
                if max_day is not None and d > max_day:
                    continue
                days.append((d, p))
            for _, path in sorted(days)[-lookback_days:]:
                try:
                    blob = path.read_bytes()
                except Exception:
                    continue
                for raw in set(_CAPTURED_AT_RE.findall(blob)):
                    ts = raw.decode("utf-8", "replace")
                    dt = _parse_capture_ts(ts)
                    if dt is None:
                        continue
                    leg = tgm.collector_bucket(dt)
                    if ts > out.get(leg, ""):
                        out[leg] = ts
        return out
    except Exception:
        return {}


def _parse_capture_ts(ts: str):
    """Parse a tape `captured_at` via core.timeutil.parse_iso_utc (L138: never
    datetime.fromisoformat directly). Returns None on anything unparseable."""
    try:
        from core.timeutil import parse_iso_utc
        return parse_iso_utc(ts)
    except Exception:
        return None


def _dead_collector_leg_diagnosis(tape_root: Path = ROOT / "tape",
                                  now=None,
                                  lookback_days: int = DEAD_LEG_LOOKBACK_DAYS,
                                  max_day: Optional[date] = None) -> Optional[Dict[str, object]]:
    """Diagnose an apparently-dead collector leg from committed tape (L117/L129). Returns None
    when there is nothing to say (no readable tape, or every scheduled leg captured within
    DEAD_LEG_SILENCE_HOURS). Otherwise a facts dict with `status` in:

      * "dead_leg"  — exactly one of DEAD_LEG_MONITORED is silent >= DEAD_LEG_SILENCE_HOURS
                      while some other leg captured within DEAD_LEG_ALIVE_HOURS. The leg is
                      NAMED.
      * "ambiguous" — BOTH scheduled legs are silent. Never guessed at a name (the L118/L120
                      attribution discipline in tape_gap_monitor.py: both-zero stays
                      unattributed), because a whole-pipe outage and two independent deaths are
                      indistinguishable from minute buckets alone.

    Offline and best-effort throughout; any exception returns None.
    """
    try:
        from datetime import datetime as _datetime, timezone as _timezone
        if now is None:
            now = _datetime.now(_timezone.utc)
        last_seen = _collector_leg_last_seen(tape_root, lookback_days=lookback_days,
                                             max_day=max_day)
        if not last_seen:
            return None

        def _age_h(iso: str) -> Optional[float]:
            dt = _parse_capture_ts(iso)
            if dt is None:
                return None
            return (now - dt).total_seconds() / 3600.0

        ages = {leg: _age_h(iso) for leg, iso in last_seen.items()}
        newest_leg = max(last_seen, key=lambda k: last_seen[k])
        newest_iso = last_seen[newest_leg]
        newest_age = ages.get(newest_leg)
        alive = sorted(leg for leg, a in ages.items()
                       if a is not None and a < DEAD_LEG_ALIVE_HOURS)
        silent = [leg for leg in DEAD_LEG_MONITORED
                  if leg not in last_seen
                  or (ages.get(leg) is not None and ages[leg] >= DEAD_LEG_SILENCE_HOURS)]
        if not silent:
            return None
        base = {
            "newest_iso": newest_iso,
            "newest_age_h": newest_age,
            "alive": alive,
            "silent": silent,
            "last_seen": last_seen,
            "ages": ages,
            "lookback_days": lookback_days,
        }
        if len(silent) == len(DEAD_LEG_MONITORED):
            base["status"] = "ambiguous"
            return base
        if not alive:
            # A single scheduled leg is silent but nothing is producing right now either —
            # not the staggered-death signature; stay quiet rather than mis-attribute.
            return None
        dead = silent[0]
        base["status"] = "dead_leg"
        base["dead"] = dead
        base["dead_last_seen"] = last_seen.get(dead)
        base["dead_silence_h"] = ages.get(dead)
        return base
    except Exception:
        return None


def dead_collector_leg_warning(diag: Optional[Dict[str, object]]) -> Optional[str]:
    """A non-gating advisory block naming a dead/stalled collector leg, else None. Pure.

    Written to be quotable verbatim by a run's digest author to a non-programmer: it says which
    leg is dead, when it was last seen, how long it has been silent, and which leg is still
    alive. It NEVER flips the exit code."""
    if not diag:
        return None
    lookback = diag.get("lookback_days")
    newest_age = diag.get("newest_age_h")
    newest_age_s = f"{newest_age:.1f}h ago" if isinstance(newest_age, float) else "unknown age"
    header = "COLLECTOR HEALTH ADVISORY (non-gating): "
    tail = (f"Newest capture anywhere in committed hourly tape: {diag.get('newest_iso')} "
            f"({newest_age_s}). Detected from committed tape only (captured_at minute-of-hour "
            f"buckets, last {lookback} day-files per family); leg signatures imported from "
            f"scripts/tape_gap_monitor.py. This is ADVISORY ONLY and does NOT affect the exit "
            f"code — a dead VPS cron cannot be fixed from a cloud run. Fix = restart the cron on "
            f"the machine that owns it. See kb/lessons/00-lessons.md L117/L129.")

    def _leg_line(leg: str) -> str:
        seen = diag.get("last_seen", {}).get(leg)  # type: ignore[union-attr]
        age = diag.get("ages", {}).get(leg)        # type: ignore[union-attr]
        if seen is None:
            return (f"  - {leg}: NO capture at all in the last {lookback} day-files "
                    f"(silent for longer than the lookback window)")
        age_s = f"{age:.1f}h" if isinstance(age, float) else "unknown"
        return f"  - {leg}: last seen {seen} ({age_s} of silence)"

    if diag.get("status") == "ambiguous":
        silent = diag.get("silent", [])
        lines = [header + "AMBIGUOUS — BOTH scheduled collector legs "
                 f"({', '.join(DEAD_LEG_MONITORED)}) have been silent for >= "
                 f"{DEAD_LEG_SILENCE_HOURS:.0f}h. NO leg is named: two independent deaths and a "
                 f"whole-pipe outage are indistinguishable from capture timestamps alone, and a "
                 f"guess here would be a false accusation (same discipline as "
                 f"tape_gap_monitor.diagnose_collector's both-zero case)."]
        lines += [_leg_line(leg) for leg in silent]  # type: ignore[union-attr]
        still = diag.get("alive") or []
        lines.append(f"  - still producing within {DEAD_LEG_ALIVE_HOURS:.0f}h: "
                     + (", ".join(still) if still else "NOTHING (whole pipe looks dark)"))
        lines.append("  " + tail)
        return "\n".join(lines)

    dead = diag.get("dead")
    silence = diag.get("dead_silence_h")
    silence_s = f"{silence:.1f}h" if isinstance(silence, float) else f">{lookback} days"
    seen_s = diag.get("dead_last_seen") or f"not within the last {lookback} day-files"
    alive = [leg for leg in (diag.get("alive") or []) if leg != dead]  # type: ignore[union-attr]
    return "\n".join([
        header + f"the '{dead}' collector leg appears DEAD.",
        f"  - dead leg: {dead} ({_leg_schedule_phrase(str(dead))})",
        f"  - last capture written by it: {seen_s}",
        f"  - silent for: {silence_s} (threshold: {DEAD_LEG_SILENCE_HOURS:.0f}h)",
        f"  - still alive: {', '.join(alive) if alive else 'none'} "
        f"(captured within the last {DEAD_LEG_ALIVE_HOURS:.0f}h), so the tape keeps growing and "
        f"nothing else looks broken — which is exactly why this outage stays invisible.",
        "  " + tail,
    ])


# ─── Ladder-size int-coercion advisory (L47: non-gating, offline-safe) ──────────

# L47: persisted orderbook_depth `yes_bids`/`no_bids` sizes are FLOATS and genuinely
# fractional (real-tape census 2026-07-25: 747,412 / 14,756,132 levels = 5.07% fractional,
# 5,832 with 0 < size < 1). Truncating one to int without an explicit rounding rule silently
# corrupts a queue-depth read. The single sanctioned coercion lives in
# `core.depth.whole_contracts_available` (documented floor rule); this advisory is a LEXICAL
# PROXY for "a NEW site coerced a ladder size", with the tested coverage and the tested blind
# spots both stated below. It is a proxy, not a decision procedure: it cannot know whether an
# arbitrary `size` name is an order-book ladder size, so it is advisory, never gating.
#
# TESTED COVERAGE — shapes an adversarial-corpus test asserts DO fire
# (`tests/test_invariants.py::test_ladder_size_coercion_fires_on_tested_shape_set`):
#   * bare/attr/subscript size-ish name: `int(size)`, `round(bid_size)`, `math.floor(sizes[i])`,
#     `ceil(rec.no_ask_size)`, `int(queue_ahead)`, `int(total_depth)`;
#   * ladder-level pair subscript: `int(level[1])`, `int(lvl[1])`, `int(bid[1])`;
#   * MULTI-subscript ladder-level: `int(no_bids[0][1])`, `int(ladder[i][1])` — added
#     2026-07-25 because `analysis/observatory/features.py:160-161` already writes exactly
#     that shape (`no_bids[0][1]` for `touch_queue`), so it is the likeliest reintroduction;
#   * NESTED cast: `int(float(size))`, `round(float(level[1]))`;
#   * `math.trunc(size)` / `trunc(size)`.
#
# KNOWN, DELIBERATE BLIND SPOTS — shapes an adversarial-corpus test asserts do NOT fire
# (`tests/test_invariants.py::test_ladder_size_coercion_known_blind_spots_are_misses`).
# These are documented holes, not oversights: each was considered and rejected because a
# lexical rule wide enough to catch it would false-positive on the real tree.
#   * bare `int(depth)` — `depth` is a legitimate ALREADY-INTEGER level COUNT field in the
#     orderbook_depth record schema, so matching it would fire on correct code;
#   * `int(row[1])` / `int(pair[1])` / `int(entry[1])` — `row`/`pair`/`entry` are ordinary
#     CSV / dict-iteration names, not ladder-specific;
#   * renamed intermediates (`for price, size in ladder: n = size; int(n)`) — needs dataflow;
#   * size-ish PREFIX not suffix (`int(size_remaining)`), and paraphrases like
#     `int(resting_qty_at_level)` — no high-precision lexical rule found;
#   * multi-LINE calls (`int(\n    size\n)`) — the scan is line-by-line;
#   * non-call coercions: `size // 1`, `'%d' % size`, `f"{size:d}"`;
#   * the L47 row's other half, an equality check against a whole-number queue position
#     (`size == 5`) — no site exists today and no precise lexical rule was found.
# Closing any of these requires an AST/dataflow pass, not a wider regex.
#
# Precision rules (this must stay at ZERO hits on the clean tree):
#   * the coerced expression must be a WHOLE simple argument — a bare name, an attribute
#     chain, subscripts, or one nested float()/int()/abs() cast — so
#     `round(size_pos[k] / n_lines, 6)` (a ratio) is NOT flagged;
#   * ALL-CAPS names are constants, never a live ladder size, so `int(MIN_DEPTH)` is NOT
#     flagged;
#   * the name must be size-ish (`*size`/`*sizes`/`*_sz`/`queue_ahead*`/`*_depth`), or a
#     `level[1]`-shaped ladder-level subscript (the second element IS the size);
#   * a BACKTICKED prose mention (`` `int(size)` ``) inside a docstring is documentation, not
#     code, and is skipped. NOTE the skip is a ONE-CHARACTER lookbehind on the char before the
#     match, so it only handles the SINGLE-backtick form; a double-backticked ``` ``int(size)``
#     ``` prose mention in a .py docstring would still be flagged. Latent precision fragility,
#     0 hits on today's tree — left as-is rather than grown into a markdown parser;
#   * comment lines and tests/ are skipped (fixtures deliberately construct bad shapes).
_LADDER_SIZE_COERCION_RE = re.compile(
    r"\b(?:int|round|floor|ceil|trunc|math\.floor|math\.ceil|math\.trunc)\s*\(\s*"
    r"(?:(?P<cast>float|int|abs)\s*\(\s*)?"
    r"(?P<expr>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\[[^\]\[]*\])*)"
    r"\s*\)?\s*(?:,|\))"
)
_SIZE_ISH_NAME_RE = re.compile(r"(?:^|_)(?:size|sizes|sz)$|^queue_ahead|_depth$", re.I)
_LADDER_LEVEL_NAME_RE = re.compile(
    r"(?:^|_)(?:level|lvl|bid|ask|rung|ladder|book)s?$", re.I
)
# The ONE site allowed to turn a ladder size into an integer (L47's explicit floor rule).
# NOTE this exempts the WHOLE FILE, not just `whole_contracts_available` — a future bare
# `int(size)` elsewhere in core/depth.py is invisible to this advisory. Accepted deliberately
# (file-level granularity matches every other exempt list here); tightening it to a
# function-level exemption would need an AST pass, not a path-prefix compare.
LADDER_SIZE_COERCION_EXEMPT = ("core/depth.py",)


def _is_ladder_size_expr(expr: str) -> bool:
    """True when `expr` (the whole single argument of an int()/round()/floor()/ceil()/trunc()
    call, with any one nested float()/int()/abs() cast already stripped) denotes an order-book
    ladder SIZE. Pure, no I/O — the precision core of the L47 advisory. See the module-level
    block above for the tested shape set AND the deliberate blind-spot set."""
    base = expr.partition("[")[0]
    subs = re.findall(r"\[([^\]\[]*)\]", expr)
    tail = base.split(".")[-1]
    if not tail or tail.isupper():   # ALL-CAPS -> a module constant, not a live size
        return False
    if _SIZE_ISH_NAME_RE.search(tail):
        return True
    # `level[1]` / `bid[1]` / `no_bids[0][1]` / `ladder[i][1]`: the LAST index selects element
    # 1 of a [price, size] pair, which IS the size.
    return (
        bool(subs)
        and subs[-1].strip() == "1"
        and bool(_LADDER_LEVEL_NAME_RE.search(tail))
    )


def _ladder_size_coercion_issues(root: Path = ROOT) -> List[str]:
    """Production sites that coerce an order-book ladder size to an integer outside the
    sanctioned `core.depth.whole_contracts_available` (L47). Best-effort/offline: any
    exception skips a file and can never poison the gate. Returns sorted `path:line`."""
    out: List[str] = []
    try:
        for p in _iter_source_files(root, exts=(".py",)):
            rel = str(p.resolve().relative_to(root.resolve())).replace("\\", "/")
            if rel in LADDER_SIZE_COERCION_EXEMPT or rel.split("/", 1)[0] == "tests":
                continue
            try:
                lines = p.read_text().splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    continue
                for m in _LADDER_SIZE_COERCION_RE.finditer(line):
                    if m.start() > 0 and line[m.start() - 1] == "`":
                        continue  # backticked prose mention in a docstring, not code
                    if _is_ladder_size_expr(m.group("expr")):
                        out.append(f"{rel}:{i}")
                        break
        return sorted(out)
    except Exception:
        return []


def ladder_size_coercion_warning(sites: List[str]) -> Optional[str]:
    """Non-gating advisory when production code int-coerces an order-book ladder size outside
    `core.depth.whole_contracts_available`, else None. Pure.

    The message states the TESTED shape set and the KNOWN blind spots, not the intent: this is
    a lexical proxy, and reporting 0 sites is evidence of PRECISION only, never of RECALL
    (L155)."""
    if not sites:
        return None
    n = len(sites)
    examples = ", ".join(sites[:3]) + (", ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} production site(s) coerce an order-book ladder SIZE to an "
        f"integer outside the sanctioned `core.depth.whole_contracts_available` (e.g. "
        f"{examples}). Persisted yes_bids/no_bids sizes are FLOATS and 5.07% of real-tape "
        f"levels are fractional (L47); a bare int()/round() silently corrupts a queue-depth "
        f"read. Keep sizes as floats, or call the helper's explicit floor rule. "
        f"COVERAGE (lexical proxy, tested shapes only): int/round/floor/ceil/trunc applied to "
        f"a size-ish name (`*size`/`*sizes`/`*_sz`/`queue_ahead*`/`*_depth`, incl. attribute "
        f"and subscript forms), to a ladder-level pair subscript (`level[1]`, `no_bids[0][1]`, "
        f"`ladder[i][1]`), or to one nested cast (`int(float(size))`). KNOWN BLIND SPOTS "
        f"(deliberate, regression-tested as misses): bare `int(depth)` (`depth` is an integer "
        f"level COUNT in the record schema), `int(row[1])`/`pair`/`entry`, renamed "
        f"intermediates, size-ish PREFIXes (`size_remaining`), multi-line calls, `size // 1` "
        f"and `'%d' % size` — a 0-site report does NOT mean the tree is clean. Advisory only "
        f"— does NOT affect the exit code. See kb/lessons/00-lessons.md L47, L155."
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


_BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
_FUNC_CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\(\)")


def _parse_lesson_rows(
    lessons_path: Path = ROOT / "kb" / "lessons" / "00-lessons.md",
) -> List[Tuple[str, str, str]]:
    """(id, lesson_text, enforcement_text) for every table row in
    kb/lessons/00-lessons.md. Best-effort/offline: a read failure returns []."""
    try:
        lines = lessons_path.read_text().splitlines()
    except Exception:
        return []
    rows: List[Tuple[str, str, str]] = []
    for line in lines:
        m = _LESSON_ID_ROW_RE.match(line)
        if not m:
            continue
        cols = line.split("|")
        if len(cols) < 6:
            continue
        rows.append((m.group(1), cols[3].strip(), cols[5].strip()))
    return rows


def _stale_unenforced_candidate_issues(
    lessons_path: Path = ROOT / "kb" / "lessons" / "00-lessons.md",
    source_root: Path = ROOT,
) -> List[str]:
    """L152's proposed follow-up: a WEAKER but assertable proxy for a stale `UNENFORCED`
    marker in kb/lessons/00-lessons.md -- a row whose enforcement was actually built by a
    later run but whose status was never flipped (the L74/L109/L123 incident).

    Scope, deliberately narrow: only rows whose ENFORCEMENT column still starts with the
    bold `**UNENFORCED**` marker (the ledger's own definition of its standing work queue,
    00-lessons.md line 9) are candidates. Within that column only (never the lesson-text
    column -- a row's own narrative often names an EXISTING function as background context,
    not as its candidate; L105 names `_segment_bounds()` from `scripts/anomaly_sweep.py` as
    the reason a proposal dies, and that would be a pure false positive if lesson text were
    in scope), extract backtick-quoted `function_name()` tokens. A bare script/module PATH
    (e.g. `scripts/invariants.py`) is deliberately NOT matched -- nearly every candidate names
    an already-existing file as the site where a new check should be ADDED, so path-existence
    alone would flag almost every open row and carry no signal. A function name is matched
    only when it contains an underscore (the codebase's private-helper naming convention),
    to skip generic single-word names (`run()`, `main()`) that would false-positive on
    unrelated same-named functions elsewhere in the tree.

    For each such candidate function name, search every tracked `.py`/`.sql` file for a
    `def <name>(` definition. A hit means the row's own proposed enforcement already exists
    somewhere in the tree -- the marker is a HIGH-PRECISION candidate for stale, though not
    proof (a same-named function could coincidentally exist for an unrelated reason; a human/
    kb-distiller pass still confirms before flipping the row, same as the L74/L109/L123
    corrections). Best-effort/offline: any failure returns [] and can never poison the gate.
    Returns one formatted string per (lesson id, function name, defining file) hit."""
    try:
        rows = _parse_lesson_rows(lessons_path)
        if not rows:
            return []
        candidates: List[Tuple[str, str]] = []  # (lesson_id, func_name)
        for lesson_id, _lesson_text, enforcement in rows:
            if not enforcement.startswith("**UNENFORCED**"):
                continue
            names = set()
            for span in _BACKTICK_SPAN_RE.findall(enforcement):
                for fn in _FUNC_CALL_RE.findall(span):
                    if "_" in fn:
                        names.add(fn)
            for fn in sorted(names):
                candidates.append((lesson_id, fn))
        if not candidates:
            return []
        def_res = {fn: re.compile(rf"^\s*def\s+{re.escape(fn)}\s*\(") for _lid, fn in candidates}
        hits: Dict[str, List[str]] = {}
        for path in _iter_source_files(source_root):
            try:
                text = path.read_text(errors="replace")
            except Exception:
                continue
            for fn, pat in def_res.items():
                if fn in hits:
                    continue
                if any(pat.match(ln) for ln in text.splitlines()):
                    hits.setdefault(fn, []).append(_rel(path))
        issues = []
        for lesson_id, fn in candidates:
            if fn in hits:
                for defining_file in hits[fn]:
                    issues.append(f"{lesson_id}: candidate `{fn}()` already defined in {defining_file}")
        return issues
    except Exception:
        return []


def stale_unenforced_candidate_warning(issues: List[str]) -> Optional[str]:
    """Non-gating advisory when an UNENFORCED lesson row's own candidate function name
    already exists in the tree -- a likely-stale marker per L152. Pure."""
    if not issues:
        return None
    n = len(issues)
    examples = "; ".join(issues[:5]) + (", ..." if n > 5 else "")
    return (
        f"warning (non-gating): {n} UNENFORCED lesson row(s) in kb/lessons/00-lessons.md "
        f"name a candidate function that already exists in the tree (e.g. {examples}) -- "
        f"likely a stale marker (L74/L109/L123 precedent: the enforcement was built by a "
        f"later run but the row's status was never flipped). Confirm before flipping -- a "
        f"same-named function can exist for an unrelated reason. Advisory only -- does NOT "
        f"affect the exit code. See kb/lessons/00-lessons.md L152."
    )


# ─── Recovery-finding dwell advisory (L157: non-gating, offline-safe) ────────
#
# L157: "no collector-recovery finding may be filed without >=24 consecutive hours of the
# expected signature bucket observed post-restart, and the finding MUST state the dwell it
# actually observed" — with a NAMED ANCHOR (L157 again: the 07-22 recovery dwelled 18.8h from
# `2026-07-21T22:41Z` or 18.1h from `2026-07-21T23:23:01Z`, "always state which anchor you are
# quoting"). A recovery claim with no dwell number is a hypothesis wearing a verdict's clothes,
# and it retires the queue's attention on a live outage.
#
# This is a LEXICAL PROXY over prose, so per L155 its coverage is only the shape set its
# constructed-negative corpus (`tests/test_recovery_dwell_advisory.py`) asserts FIRE — a
# 1-issue report is evidence of PRECISION, never of recall. Deliberately NON-GATING: no regex
# can adjudicate an English recovery claim, so it must not be able to block a run.

RECOVERY_DWELL_MIN_HOURS = 24.0
RECOVERY_ANCHOR_WINDOW_LINES = 2       # a named anchor must sit on/next to the dwell sentence
RECOVERY_HEADLINE_LEAD_LINES = 10      # how far in we look for the H1 (front-matter tolerance)
RECOVERY_ESCAPE_HATCH_LEAD_LINES = 40  # supersession marker must be up top, not buried

# A recovery/return-to-service claim...
_RECOVERY_TERM_RE = re.compile(
    # "recovery TOOLING/script/plan/..." is a tooling finding, not a recovery VERDICT — the one
    # false positive a 27-shape adversarial probe found, narrowed here rather than accepted.
    r"(recover(?:ed|y|s|ing)?\b"
    r"(?!\s+(?:tool|tooling|script|plan|playbook|procedure|checklist|protocol|guide|runbook))"
    r"|restored|revived|resurrect\w*"
    r"|back\s+(?:online|up|alive)|(?:came|comes|is|are)\s+back\b"
    r"|(?:alive|up|online|healthy|working|producing|capturing|running|green|back)\s+again"
    r"|resumed|self-?heal(?:ed|s|ing)?|no\s+longer\s+(?:dead|down))",
    re.I,
)
# ...about a data-collection subject. Both must be in the HEADLINE for the finding to be
# recovery-class (see `_recovery_dwell_issues.__doc__` for why the body is out of scope).
_RECOVERY_SUBJECT_RE = re.compile(
    r"(collector|collection|cron|captur\w*|tape|pipeline|feed|leg|vps|cloud|scheduler"
    r"|runner|hourly[_ -]?pass|ingest\w*|sweep|pass)",
    re.I,
)
# A duration quantified in HOURS ("24h", "36 hrs", "48-hour"). Days/minutes are deliberately
# NOT accepted — L157's threshold is stated in consecutive hours and that is the unit a
# recovery finding must report in.
_HOURS_QTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:h\b|hrs?\b|hours?\b)", re.I)
# ...that is claimed as an OBSERVED DWELL, not just any duration mentioned in the document
# (a recovery finding routinely quotes the preceding OUTAGE length in hours; that is not a
# dwell). The number must share a line with one of these.
_DWELL_CONTEXT_RE = re.compile(
    r"(dwell\w*|consecutive|continuous\w*|uninterrupted|unbroken|sustained|straight"
    r"|uptime|stable|steady|no\s+gaps?|without\s+a\s+gap|gap-free"
    r"|since\s+(?:the\s+)?(?:restart|recovery|fix|restore\w*)|post-?restart|post-?recovery)",
    re.I,
)
# A named anchor: an explicit UTC moment. A bare calendar date is NOT an anchor (it names a
# day, not the instant a dwell is measured from), and neither is a relative phrase
# ("since the restart") — that imprecision is exactly what L157 was written about.
_ANCHOR_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
# Escape hatch (L162 names the need for one), kept deliberately narrow: an ALL-CAPS
# supersession/retraction/correction marker at the start of a line in the document's head,
# naming the lesson ID or finding that supersedes it.
_SUPERSESSION_MARKER_RE = re.compile(
    r"^\s*(?:<!--\s*)?(?:>\s*)?\**\s*(SUPERSEDED|RETRACTED|WITHDRAWN|CORRECTED)\b"
)
_SUPERSESSION_REF_RE = re.compile(r"(\bL\d+\b|findings/[\w.\-/]+\.md)")


def _recovery_headline(path: Path, lines: List[str]) -> str:
    """The finding's HEADLINE: its filename slug plus the first `# ` H1 found in the leading
    `RECOVERY_HEADLINE_LEAD_LINES` lines. Pure."""
    h1 = ""
    for line in lines[:RECOVERY_HEADLINE_LEAD_LINES]:
        if line.startswith("# "):
            h1 = line[2:]
            break
    return f"{path.stem.replace('-', ' ')} \n{h1}"


def _recovery_dwell_issues(findings_dir: Path = ROOT / "findings") -> List[Tuple[str, str]]:
    """Recovery-class findings that violate L157: they claim a collector recovery in their
    HEADLINE without stating an observed dwell of >= `RECOVERY_DWELL_MIN_HOURS` hours, and/or
    without a named anchor (an explicit UTC timestamp) the dwell is measured from.

    SCOPING — headline only, on purpose. Recovery-class membership is decided from the
    filename slug + the first `# ` H1 ONLY, never the body. Measured on the 2026-07-25 tree,
    16 of 83 `findings/*.md` contain the substring "recover" somewhere in their body (usually
    quoting or refuting an earlier recovery claim) while exactly ONE claims recovery in its
    headline. A body-wide match would therefore be a ~16x precision disaster of exactly the
    kind L155 warns about, and it would fire hardest on the findings that are CORRECTING a bad
    recovery claim. The headline is also the right semantic unit: L157 is about a finding whose
    VERDICT is "recovered", and a finding's verdict lives in its title.

    Both halves of L157 are required, and the reason string names which is missing:
      * a STATED DWELL — an hours-quantified duration >= the threshold, sharing a line with
        dwell vocabulary (`dwell`/`consecutive`/`uptime`/`since the restart`/...). A bare
        duration elsewhere in the document does not count: a recovery finding routinely quotes
        the preceding OUTAGE length in hours, which is not a dwell. Durations stated in days or
        minutes do not count either — L157's threshold is in consecutive hours.
      * a NAMED ANCHOR — a `YYYY-MM-DD hh:mm` UTC moment on the dwell line or within
        `RECOVERY_ANCHOR_WINDOW_LINES` lines of it. A bare date, or a relative phrase like
        "since the restart", is not an anchor.

    ESCAPE HATCH (narrow, L162): a finding that records its own supersession is skipped —
    a line in its first `RECOVERY_ESCAPE_HATCH_LEAD_LINES` lines that STARTS with an ALL-CAPS
    `SUPERSEDED`/`RETRACTED`/`WITHDRAWN`/`CORRECTED` (optionally behind `>`/`**`/`<!--`) AND
    names the superseding lesson ID (`L\\d+`) or `findings/<file>.md` on the same line. Caps +
    line-start + a named reference are all required so that ordinary prose ("this supersedes
    the confidence of L129") cannot silence the check by accident.

    Best-effort/offline: no network, no git, no subprocess; any per-file exception skips that
    file and can never poison the gate. Returns sorted `(relpath, reason)` pairs."""
    out: List[Tuple[str, str]] = []
    try:
        if not findings_dir.is_dir():
            return out
        for path in sorted(findings_dir.glob("*.md")):
            try:
                if not path.is_file():
                    continue
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                headline = _recovery_headline(path, lines)
                if not (_RECOVERY_TERM_RE.search(headline)
                        and _RECOVERY_SUBJECT_RE.search(headline)):
                    continue
                if any(_SUPERSESSION_MARKER_RE.match(ln) and _SUPERSESSION_REF_RE.search(ln)
                       for ln in lines[:RECOVERY_ESCAPE_HATCH_LEAD_LINES]):
                    continue
                dwell_lines = [
                    i for i, ln in enumerate(lines)
                    if _DWELL_CONTEXT_RE.search(ln)
                    and any(float(q) >= RECOVERY_DWELL_MIN_HOURS
                            for q in _HOURS_QTY_RE.findall(ln))
                ]
                reasons: List[str] = []
                if not dwell_lines:
                    reasons.append(
                        f"no stated dwell of >= {RECOVERY_DWELL_MIN_HOURS:g}h "
                        f"(an hours-quantified duration on a dwell/consecutive/uptime line)"
                    )
                    if not any(_ANCHOR_TS_RE.search(ln) for ln in lines):
                        reasons.append("no named anchor (no UTC timestamp anywhere in the finding)")
                elif not any(
                    _ANCHOR_TS_RE.search(ln)
                    for i in dwell_lines
                    for ln in lines[max(0, i - RECOVERY_ANCHOR_WINDOW_LINES):
                                    i + RECOVERY_ANCHOR_WINDOW_LINES + 1]
                ):
                    reasons.append(
                        f"dwell stated but no named anchor (a YYYY-MM-DD hh:mm UTC moment) "
                        f"within +/-{RECOVERY_ANCHOR_WINDOW_LINES} lines of it"
                    )
                if reasons:
                    try:
                        # Repo-relative label when the finding lives under ROOT; otherwise
                        # (a tmp_path corpus in tests) the plain path — `relative_to` RAISES
                        # off-tree, and swallowing that would silently drop every issue.
                        rel = str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
                    except Exception:
                        rel = str(path)
                    out.append((rel, "; ".join(reasons)))
            except Exception:
                continue
        return sorted(out)
    except Exception:
        return []


def recovery_dwell_warning(issues: List[Tuple[str, str]]) -> Optional[str]:
    """Non-gating advisory when a recovery-class finding violates L157's dwell/anchor rule,
    else None. Pure. States its TESTED scope, not its intent (L155)."""
    if not issues:
        return None
    n = len(issues)
    detail = "; ".join(f"{rel} ({why})" for rel, why in issues[:3]) + (", ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} recovery-class finding(s) declare a collector recovered "
        f"without L157's evidence: {detail}. A point observation cannot distinguish a fixed "
        f"collector from one that dies again tomorrow — the 2026-07-22 'RECOVERED' verdict "
        f"dwelled 18.8h (from 2026-07-21T22:41Z) / 18.1h (from 2026-07-21T23:23:01Z) and then "
        f"went silent 61.7h unnoticed. State >= {RECOVERY_DWELL_MIN_HOURS:g}h of observed "
        f"post-restart dwell AND the anchor you measured it from. "
        f"COVERAGE (lexical proxy, headline-scoped, tested shapes only): recovery-class = "
        f"filename slug or first H1 carrying a recovery term AND a collection subject; a dwell "
        f"= an hours-quantified duration on a dwell/consecutive/uptime line; an anchor = a "
        f"YYYY-MM-DD hh:mm moment within +/-{RECOVERY_ANCHOR_WINDOW_LINES} lines of it. "
        f"KNOWN BLIND SPOTS (deliberate, regression-tested as misses in "
        f"tests/test_recovery_dwell_advisory.py): repair-verb headlines ('is fixed', "
        f"'repaired' — too close to ordinary bug-fix titles to match safely), a recovery claim "
        f"made only in the body or an H2 (headline-scoped by design), and an OUTAGE duration "
        f">= the threshold sharing a line with dwell wording (read as a dwell). Measured recall "
        f"on a 22-shape adversarial corpus: 18/22 — a 1-issue report is PRECISION evidence, "
        f"not recall (L155). "
        f"Advisory only — does NOT affect the exit code. See kb/lessons/00-lessons.md L157."
    )


# ─── Hand-rolled binary settlement-result advisory (L52: non-gating, offline) ─
#
# L52 (2026-07-14): Kalshi sports settlement results are NOT always binary. Q26's live pull of
# `fetch_kalshi_settled` over 458 settled markets across 7 sports series returned 8 rows with
# `result: "scalar"` — not `result in {"yes","no"}`. Code that reads a settled market's result
# by comparing it to the bare string "yes"/"no" therefore silently classifies every non-binary
# row as the LOSING side of a yes/no hit-rate or P&L calculation, instead of excluding it.
# The sanctioned fix is `core.settlement` (`filter_binary_settlements` / `binary_outcome` /
# `require_binary_result`), which filters on the result field's ACTUAL value.
#
# This is a LEXICAL, LINE-SCOPED proxy, and it is deliberately narrow:
#   * a HIT needs BOTH an equality/inequality against a `"yes"`/`"no"` literal AND a
#     settlement token (`result`/`results`/`settle*`/`outcome`) on the SAME line. The same-line
#     requirement is the whole precision story — `execution/fill_models.py` compares an ORDER
#     SIDE (`side == "yes"`, `order.side != "no"`) on lines with no settlement token, and those
#     must never be reported. Pinned in tests/test_settlement_result_advisory.py.
#   * a file is GUARDED (and dropped ENTIRELY) when it anywhere mentions a `"scalar"` literal,
#     applies an `in`/`not in` membership test over a 2-element ("yes","no") collection, or
#     references the sanctioned helper. File-level, not line-level: see BLIND SPOTS below.
# Deliberate blind spots (regression-tested as MISSES, so widening the rule has to delete a
# test on purpose rather than by accident):
#   * the settlement token on an EARLIER line than the comparison —
#     `scripts/probe_ladder_coherence.py:140` (`if res == "yes":`, where `res` is assigned from
#     a settlement record two lines up) is a genuine unguarded site this rule does not see.
#     Closing it needs dataflow, not a wider regex;
#   * file-level guard granularity: ONE `"scalar"` mention anywhere exempts every other
#     hand-rolled comparison in that file;
#   * membership over a >2-element or dynamically-built collection, `result.startswith("y")`,
#     `dict.get("result") == "yes"` split across lines, and `match`/`case` forms.
_BINARY_RESULT_CMP_RE = re.compile(
    r"""(?:(?:==|!=)\s*(['"])(?:yes|no)\1)|(?:(['"])(?:yes|no)\2\s*(?:==|!=))"""
)
_SETTLEMENT_TOKEN_RE = re.compile(r"\b(?:results?|settle\w*|outcome)\b", re.I)
_SCALAR_LITERAL_RE = re.compile(r"""['"]scalar['"]""")
# `x in ("yes","no")` / `x not in {"no","yes"}` / `[...]` — an EXPLICIT 2-element binary filter.
_BINARY_MEMBERSHIP_RE = re.compile(
    r"""\b(?:not\s+in|in)\s*[\(\[\{]\s*(['"])(?:yes|no)\1\s*,\s*"""
    r"""(['"])(?:yes|no)\2\s*,?\s*[\)\]\}]"""
)
_SETTLEMENT_HELPER_RE = re.compile(
    r"core\.settlement|from\s+core\s+import\s+settlement"
    r"|is_binary_result|binary_outcome|filter_binary_settlements"
    r"|filter_binary_results_map|require_binary_result"
)
# The sanctioned home of the binary-result predicate itself (it must compare against the
# literals to define them). Whole-file exemption, same shape as LADDER_SIZE_COERCION_EXEMPT.
HANDROLLED_BINARY_RESULT_EXEMPT = ("core/settlement.py",)


def _docstring_line_numbers(text: str) -> set:
    """1-based line numbers spanned by module/class/function DOCSTRINGS in `text`, via `ast`.

    Prose that merely DISCUSSES a settlement comparison is documentation, not a hand-rolled
    read: `scripts/weather_rehab_s5.py` lines 107 and 112 say "YES pays $1 if result=='yes'"
    inside the module docstring, while its line 508 really does compute
    `[tk for tk in tickers if members[tk]["result"] == "yes"]`. A comment-prefix test cannot
    tell those apart; the AST can. Falls back to NO exclusion when the file does not parse —
    the honest degradation is to over-report, never to skip a real site. Pure."""
    out: set = set()
    try:
        tree = ast.parse(text)
    except Exception:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return out


def _handrolled_binary_result_sites(root: Path = ROOT) -> List[str]:
    """Production lines that decide a settled market's outcome by comparing it to a bare
    `"yes"`/`"no"` literal, in files carrying no binary-result guard (L52).

    See the module-level block above for the exact HIT rule, the file-level GUARD set, and the
    deliberate blind spots. `tests/` is skipped (fixtures construct the bad shape on purpose)
    and `HANDROLLED_BINARY_RESULT_EXEMPT` exempts the sanctioned helper itself.

    Best-effort/offline: no network, no git, no subprocess; any per-file exception skips that
    file and can never poison the gate. Returns sorted `relpath:line` labels."""
    out: List[str] = []
    try:
        for p in _iter_source_files(root, exts=(".py",)):
            try:
                rel = str(p.resolve().relative_to(root.resolve())).replace("\\", "/")
            except Exception:
                continue
            if rel in HANDROLLED_BINARY_RESULT_EXEMPT or rel.split("/", 1)[0] == "tests":
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                if (_SCALAR_LITERAL_RE.search(text)
                        or _BINARY_MEMBERSHIP_RE.search(text)
                        or _SETTLEMENT_HELPER_RE.search(text)):
                    continue  # file carries an explicit binary-result guard
                doc_lines = _docstring_line_numbers(text)
                for i, line in enumerate(text.splitlines(), 1):
                    if i in doc_lines or line.lstrip().startswith("#"):
                        continue
                    if (_BINARY_RESULT_CMP_RE.search(line)
                            and _SETTLEMENT_TOKEN_RE.search(line)):
                        out.append(f"{rel}:{i}")
            except Exception:
                continue
        return sorted(out)
    except Exception:
        return []


def handrolled_binary_result_warning(sites: List[str]) -> Optional[str]:
    """Non-gating advisory when production code hand-rolls a binary settlement-result read
    outside `core.settlement` (L52), else None. Pure.

    States its TESTED shape set and its known misses, not its intent: a LOW count is evidence
    of PRECISION only, never of RECALL (L155)."""
    if not sites:
        return None
    n = len(sites)
    examples = ", ".join(sites[:3]) + (", ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} production site(s) decide a settled market's outcome by "
        f"comparing a result field to a bare \"yes\"/\"no\" literal, with no binary-result "
        f"guard anywhere in the file (e.g. {examples}). Kalshi settlement is NOT always "
        f"binary — Q26's live pull of 458 settled markets across 7 sports series returned 8 "
        f"with result:\"scalar\" — so an unfiltered comparison silently books every "
        f"non-binary row as the losing side of a yes/no hit-rate or P&L. Filter on the result "
        f"field's actual value via core.settlement.filter_binary_settlements / "
        f"core.settlement.binary_outcome. "
        f"COVERAGE (lexical proxy, line-scoped, tested shapes only): an `==`/`!=` against a "
        f"'yes'/'no' string literal (either operand order) sharing ONE line with a settlement "
        f"token (`result`/`results`/`settle*`/`outcome`); docstring lines are excluded via an "
        f"AST pass and comment lines and tests/ are skipped. "
        f"KNOWN BLIND SPOTS (deliberate, regression-tested as misses in "
        f"tests/test_settlement_result_advisory.py): the settlement token on an EARLIER line "
        f"than the comparison — scripts/probe_ladder_coherence.py:140 (`if res == \"yes\":`) "
        f"is a genuine unguarded settlement read this line-scoped rule does NOT report; "
        f"file-level guard granularity, where a single 'scalar' literal / ('yes','no') "
        f"membership test / core.settlement reference ANYWHERE in a file exempts every other "
        f"hand-rolled comparison in it; and non-comparison forms "
        f"(`result.startswith`, match/case, membership over a dynamically built collection). "
        f"A low or zero count is PRECISION evidence, not RECALL (L155). "
        f"Advisory only — does NOT affect the exit code. See kb/lessons/00-lessons.md L52, "
        f"L155."
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
        # L117/L129 advisory: one of the two staggered collector legs (VPS :23 / cloud :53)
        # apparently dead — computed from committed tape's captured_at minute buckets. Loud but
        # NON-GATING: a dead VPS cron is un-fixable from a cloud run, so gating would halt the
        # research loop for the whole outage.
        # The whole stanza is wrapped in `except BaseException` — not decoration: the
        # diagnosis self-guards, but the FORMATTER and the stderr write did not, so a raise
        # inside either (or a non-str return, which makes `+ "\n"` a TypeError) would have
        # reached the exit code and turned a non-gating advisory into a gate. BaseException,
        # not Exception, because tape_gap_monitor.py is exec'd dynamically and a SystemExit
        # raised at its module level would otherwise propagate. Degrades to one stderr note.
        try:
            collector_warning = dead_collector_leg_warning(_dead_collector_leg_diagnosis())
            if collector_warning:
                sys.stderr.write(collector_warning + "\n")
        except BaseException:
            sys.stderr.write("note: collector-health advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
        # L138 advisory: production datetime.fromisoformat sites bypassing core.timeutil
        # .parse_iso_utc (a latent Python-3.9 short-fraction/Z crash). Non-gating.
        iso_warning = raw_datetime_fromisoformat_warning(_raw_datetime_fromisoformat_sites())
        if iso_warning:
            sys.stderr.write(iso_warning + "\n")
        # L47 advisory: a production site coercing an order-book ladder SIZE to an integer
        # outside core.depth.whole_contracts_available (sizes are floats, 5.07% fractional).
        # Non-gating — stderr only, never flips the exit code.
        ladder_warning = ladder_size_coercion_warning(_ladder_size_coercion_issues())
        if ladder_warning:
            sys.stderr.write(ladder_warning + "\n")
        # L147 advisory: kb/lessons/00-lessons.md assigning the same lesson ID to more than
        # one row (2026-07-24 incident: L130/L131 each collided). Non-gating — stderr only.
        dup_lesson_warning = duplicate_lesson_id_warning(_duplicate_lesson_id_issues())
        if dup_lesson_warning:
            sys.stderr.write(dup_lesson_warning + "\n")
        # L152 advisory: an UNENFORCED lesson row whose own candidate function name already
        # exists in the tree (a high-precision proxy for a stale marker — the L74/L109/L123
        # incident). Non-gating — stderr only.
        stale_warning = stale_unenforced_candidate_warning(_stale_unenforced_candidate_issues())
        if stale_warning:
            sys.stderr.write(stale_warning + "\n")
        # L157 advisory: a recovery-class finding (headline claims a collector recovered) with
        # no stated >=24h post-restart dwell and/or no named anchor. Non-gating by construction
        # — no regex can adjudicate an English recovery claim — and wrapped like the collector
        # -health stanza so neither the formatter raising nor a non-str return can reach the
        # exit code (the DEFECT-1 lesson from the L156 advisory).
        try:
            dwell_warning = recovery_dwell_warning(_recovery_dwell_issues())
            if dwell_warning:
                sys.stderr.write(dwell_warning + "\n")
        except BaseException:
            sys.stderr.write("note: recovery-dwell advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
        # L52 advisory: a production site deciding a settled market's outcome by comparing a
        # result field to a bare "yes"/"no" literal, in a file with no binary-result guard
        # (8 of 458 settled sports markets returned result:"scalar"). Non-gating — stderr
        # only. Wrapped in `except BaseException` like the collector-health and dwell stanzas:
        # the detector self-guards, but a raise in the FORMATTER or a non-str return (making
        # `+ "\n"` a TypeError) would otherwise reach the exit code and turn a non-gating
        # advisory into a gate — the L156 DEFECT-1 lesson.
        try:
            binres_warning = handrolled_binary_result_warning(_handrolled_binary_result_sites())
            if binres_warning:
                sys.stderr.write(binres_warning + "\n")
        except BaseException:
            sys.stderr.write("note: binary-settlement-result advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
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
