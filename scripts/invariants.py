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
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Set, Tuple

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


def _excluded_relative_to(root: Path, p: Path) -> bool:
    """True if `p` sits under an EXCLUDE_DIRS directory *inside* `root`.

    The exclusion MUST be judged on the path RELATIVE to the repo root, never on the absolute
    path (the 2026-08-02 defect): every autonomous agent run of this repo executes from a git
    worktree at `.claude/worktrees/agent-*`, whose ABSOLUTE parts contain both `.claude` and
    `worktrees` — so an absolute-parts test excluded the entire repository and made
    `scan_tree()` (the Hard-Rule #1/#2/#3 static gate) and every source-scanning advisory
    silently return 0 issues over 0 files. A vacuous scan reports the same thing as a clean
    one. Falls back to the absolute test only if `p` is not under `root` at all."""
    try:
        rel = p.resolve().relative_to(root.resolve())
    except Exception:
        return any(part in EXCLUDE_DIRS for part in p.parts)
    return any(part in EXCLUDE_DIRS for part in rel.parts)


def _iter_source_files(root: Path = ROOT, exts: Tuple[str, ...] = (".py", ".sql")) -> List[Path]:
    out = []
    for p in root.rglob("*"):
        if p.is_dir() or p.suffix not in exts:
            continue
        if _excluded_relative_to(root, p):
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


# ─── Private WS-channel subscription gate (L145's residual half, 2026-08-01) ──
#
# L145 sanctioned read-only authenticated market-data auth in `collection/` on an EXPLICIT
# two-part premise: "no order verb AND no private/fill channel subscription". The
# order-verb half became `inv_order_endpoints_confined`'s ws_depth branch (2026-07-23,
# issue #157). The private-channel half was never enforced — it lived only as prose in
# `collection/ws_depth.py`'s module docstring ("never subscribes to a user/private channel
# (fills, orders, positions)"), which is exactly the "memory file" CLAUDE.md's prime
# directive #3 says must become an assertion. `DEFAULT_CHANNELS` is a plain module tuple and
# `run(..., channels=...)` a plain kwarg, so one edit turns a read-only collector into an
# account-data subscriber with a green gate.
#
# Kalshi's private/user WS channel names, per `kb/kalshi-api/02-rest-and-websocket.md`
# ("user orders, user fills, market positions, order-group updates"). That KB page states
# outright that the exact wire spellings are NOT pinned from the public index, so this list
# is best-effort over the documented families, not an exhaustive pin — it is a ratchet
# against the realistic regression, not a proof of absence.
_PRIVATE_WS_CHANNEL_LITERAL_RE = re.compile(
    r'["\'](?:fills?|user_fills?|market_positions?|user_orders?'
    r'|order_group_updates?)["\']'
)
# The context token that makes such a literal a CHANNEL NAME rather than a dict key. Matched
# as an underscore-delimited SEGMENT (the fee-rule convention) so `DEFAULT_CHANNELS`,
# `subscribe_command`, and `"channels"` all count. This context requirement is load-bearing,
# not decoration: a bare literal match fires on 23 innocent sites in this repo today
# (`record_kind = "fill"` in the paper tier, `report["fill"]` in five probes,
# `"fills": [...]` in `execution/paper_broker.py`), while the two-part match fires on none.
_WS_CHANNEL_CONTEXT_RE = re.compile(
    r'(?i)\b(?:[a-z0-9]+_)*(?:channel|channels|subscribe)(?:_[a-z0-9]+)*\b'
)

_BRACKET_OPEN, _BRACKET_CLOSE = "([{", ")]}"


def _bracket_joined_lines(text: str) -> List[Tuple[int, str]]:
    """(start_lineno, logical_line) with open-bracket continuations joined.

    Every other static rule here is physical-line-based, which is fine when the banned token
    and its context share a line. A channel tuple does not:

        DEFAULT_CHANNELS = (
            "orderbook_delta",
            "fill",              <- banned literal, no context token in sight
        )

    so this rule (and only this rule) scans a joined view. Comment-only and SENTINEL lines
    contribute no text and no bracket depth — a `#` bracket is not syntax, and a SENTINEL
    rule-definition line is exempt by the file-wide convention. An unterminated bracket at
    EOF still yields its buffer rather than being dropped."""
    out: List[Tuple[int, str]] = []
    buf = ""
    start = 1
    depth = 0
    for i, ln in enumerate(text.splitlines(), 1):
        core = "" if (SENTINEL in ln or ln.lstrip().startswith("#")) else ln
        if depth == 0:
            buf, start = core, i
        else:
            buf += " " + core.strip()
        for ch in core:
            if ch in _BRACKET_OPEN:
                depth += 1
            elif ch in _BRACKET_CLOSE:
                depth = max(0, depth - 1)
        if depth == 0:
            out.append((start, buf))
    if depth:
        out.append((start, buf))
    return out


def inv_no_private_ws_channel_subscription(path: Path, text: str) -> Optional[str]:
    """L145 residual: no Kalshi PRIVATE/user WS channel may be subscribed outside
    execution/kalshi_client.py. `collection/ws_depth.py`'s auth-header sanction rests on the
    collector being market-data-only; subscribing to `fill` / `market_positions` /
    `user_orders` would make it an account-data client under a collector's name, with the
    order-verb rule still green (no order verb is needed to read your own fills). Exempt:
    execution/kalshi_client.py (the sanctioned live client, unbuilt — a live client legitimately
    watches its own fills) and tests/test_ws_depth.py, pre-emptively, because L145's own
    root cause was PR #153 exempting two source files but not their tests. HONEST LIMIT: a
    dynamically-constructed channel name (`channels=[cfg["chan"]]`) is invisible to any static
    check — this closes the source-literal path, not the runtime one."""
    if _file_excluded(path) or _rel(path) in (SANCTIONED["order_endpoints"],
                                              "tests/test_ws_depth.py"):
        return None
    hits = [(i, ln) for i, ln in _bracket_joined_lines(text)
            if _PRIVATE_WS_CHANNEL_LITERAL_RE.search(ln)
            and _WS_CHANNEL_CONTEXT_RE.search(ln)]
    return _fmt(path, hits,
                "private/user Kalshi WS channel in a subscribe context outside "
                "execution/kalshi_client.py — lesson L145: the collector auth-header sanction "
                "covers READ-ONLY market data only (orderbook_delta/ticker/trade/"
                "market_lifecycle); fills/orders/positions are account data") if hits else None


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
    ("no_private_ws_channel_subscription", inv_no_private_ws_channel_subscription),
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


# ─── Single-hour gate IDEMPOTENCE advisory (L221: non-gating, offline-safe) ──────────
#
# L144's meta-guard above and L74's daily-gap check together cover ONE half of what
# `if ts.hour == N:` does wrong — the ZERO-passes-outside-the-hour half that freezes a family.
# L221 recorded the other half: the same line is a RATE gate, not an IDEMPOTENCE gate, so it
# admits UNBOUNDED passes inside its hour. Its measured cost on `econ_prints` was 1,720 lines
# collapsing to 785 distinct payloads (54.4% byte-redundant re-capture of a monthly-cadence
# print) plus five fully-lost calendar days, from one predicate.
#
# The check lives in `scripts/tape_gap_monitor.py::single_hour_leg_idempotence` (its coverage
# limits and the burst-window exclusion are documented there and restated in every report's own
# `coverage_note`); this is only the surface that makes it visible on the one command every
# autonomous run is required to run. Legs and their tape families come from
# `SINGLE_HOUR_LEG_FAMILIES` above; each leg's HOUR is parsed out of `collection/hourly_pass.py`
# so the number is never re-declared here and cannot desync from the collector (the same
# single-source discipline as `_TS_HOUR_EQ_RE`).
#
# NON-GATING, deliberately: these are historical properties of already-committed append-only
# tape that no run can repair, and the real fix — a once-per-day dedup KEY on the write path —
# is a live-collector change outside a research run's lane (and overlaps the `daily_leg_due()`
# design already under Ryan review in PR #165). It PRINTS; it never flips the exit code.

_UTC_HOUR_CONST_RE = re.compile(r"^([A-Z][A-Z0-9_]*_UTC_HOUR)\s*=\s*(\d+)\s*(?:#.*)?$", re.M)


def _single_hour_leg_gate_hours(
        hourly_pass_path: Path = ROOT / "collection" / "hourly_pass.py",
        source: Optional[str] = None,
        known: Optional[Dict[str, Tuple[str, ...]]] = None,
) -> Dict[str, int]:
    """`tape/<family>` -> the UTC hour its single-hour leg is gated on, read off
    `collection/hourly_pass.py`'s own `<NAME>_UTC_HOUR = <int>` constants (never re-declared
    here). A constant that is registered in `known` but absent from the source is SKIPPED,
    not defaulted — guessing an hour would silently audit the wrong window. Best-effort:
    any failure returns {}. Pure given `source`."""
    known = SINGLE_HOUR_LEG_FAMILIES if known is None else known
    try:
        if source is None:
            source = hourly_pass_path.read_text(encoding="utf-8")
        hours = {m.group(1): int(m.group(2)) for m in _UTC_HOUR_CONST_RE.finditer(source)}
        out: Dict[str, int] = {}
        for const, fams in known.items():
            h = hours.get(const)
            if h is None or not (0 <= h <= 23):
                continue
            for fam in fams:
                out[fam] = h
        return out
    except Exception:
        return {}


def _single_hour_leg_idempotence_issues(
        tape_root: Path = ROOT / "tape",
        gate_hours: Optional[Dict[str, int]] = None,
) -> List[str]:
    """One issue label per single-hour-gated family whose committed tape shows the gate
    admitted MORE THAN ONE pass on some day (L221), excluding declared burst windows.
    Best-effort/offline: any failure returns [] and can never poison the gate."""
    try:
        tgm = _load_tape_gap_monitor()
        if tgm is None:
            return []
        hours = _single_hour_leg_gate_hours() if gate_hours is None else gate_hours
        issues: List[str] = []
        for fam in sorted(hours):
            rep = tgm.single_hour_leg_idempotence(tape_root, fam, hours[fam])
            if not rep or rep.get("verdict") != "OVER_CAPTURE":
                continue
            issues.append(
                f"{fam} (gate hour {hours[fam]}Z): up to "
                f"{rep['max_passes_per_day_excl_burst']} non-burst pass(es) in ONE day "
                f"(intended 1) on {rep['n_days_over_capture_excl_burst']}/{rep['n_days']} "
                f"day(s); {rep['gate_attributable_redundant_line_fraction']:.1%} of its "
                f"{rep['n_lines']} lines are gate-attributable byte-redundant re-capture")
        return issues
    except Exception:
        return []


def single_hour_leg_idempotence_warning(issues: List[str]) -> Optional[str]:
    """A non-gating advisory when a once-per-UTC-day collector leg's committed tape proves
    its hour-equality gate admitted repeat passes (L221), else None. Pure."""
    if not issues:
        return None
    n = len(issues)
    body = "".join(f"\n  - {i}" for i in issues[:6])
    more = f"\n  - ... and {n - 6} more" if n > 6 else ""
    return (
        f"warning (non-gating): {n} single-hour collector leg(s) show their `if ts.hour == N` "
        f"gate is a RATE gate, not an IDEMPOTENCE gate — it admitted repeat passes on the same "
        f"UTC day and the extra passes re-captured an unchanged payload:{body}{more}\n"
        f"  Declared burst-trigger windows are EXCUSED (padded), so these counts exclude "
        f"sanctioned re-capture and under-report rather than over-report. The verdict measure "
        f"is passes-per-DAY, not passes-in-the-gate-hour, because a leg landing ~40min after "
        f"pass start can stamp `captured_at` in the next hour (L222). Byte-redundancy is a "
        f"proxy for wasted capture, never proof of WHICH caller fired — only an on-record "
        f"`capture_source` (L222 candidate 1) can attribute a pass. Computed from committed "
        f"tape only via scripts/tape_gap_monitor.py::single_hour_leg_idempotence; full limits "
        f"in that report's own coverage_note. Fix = a once-per-day dedup KEY per leg (never an "
        f"hour predicate). Advisory only — does NOT affect the exit code. "
        f"See kb/lessons/00-lessons.md L221."
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


# L269 (2026-08-03): a declared burst trigger deliberately re-fires the collectors every
# 60-120s inside its window, and those passes carry whatever minute-of-hour they happen to land
# on. A single FOMC-burst pass at :29 therefore read as a live "vps" pass and reset the whole
# leg's apparent freshness — `--full` announced "silent for: 104.7h" from
# 2026-07-29T18:29:45Z (the kalshi-burst-fomc-0729 window, families crypto_hourly /
# polymarket_macro_pairs) while the families NO declared trigger covers put the honest last
# vps-bucket capture at 2026-07-22T17:29:49Z, ~273.9h — a 2.6x understatement of a real outage.
# The exclusion below is the same blind-spot fix L213 already gave `slot_cadence_by_time_of_day`,
# and it reuses tape_gap_monitor's ONE copy of the window table + pad rather than a second one.
def _family_burst_windows(tgm, family: str) -> Optional[List[Tuple[object, object]]]:
    """Declared, PADDED burst windows during which `family` is deliberately re-captured, read
    from `tape_gap_monitor._burst_windows_for_family` (the single home of BURST_TRIGGER_WINDOWS
    and BURST_WINDOW_PAD_S — never re-listed here, same discipline as COLLECTOR_MINUTE_BUCKETS).

    Returns ``None`` — a DISTINCT "exclusion table unavailable", never an empty list — when the
    helper is missing or raises. The caller then degrades to the OLD count-everything behaviour:
    a missing exclusion table must leave the advisory slightly optimistic, never blank it."""
    try:
        fn = getattr(tgm, "_burst_windows_for_family", None)
        if fn is None:
            return None
        return list(fn(family))
    except Exception:
        return None


def _collector_leg_last_seen(tape_root: Path = ROOT / "tape",
                             lookback_days: int = DEAD_LEG_LOOKBACK_DAYS,
                             max_day: Optional[date] = None,
                             exclude_burst_windows: bool = True,
                             stats: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Newest `captured_at` per collector leg ("vps"/"cloud"/"other"), scanned from committed
    tape only (no network, no git). Legs are bucketed by minute-of-hour using
    tape_gap_monitor.COLLECTOR_MINUTE_BUCKETS; families are its kind=="hourly-dual" entries.
    `max_day` (optional) restricts the scan to `dt=<date>.jsonl` files on or before that day —
    used by tests to pin a FIXED historical slice so a real-tape assertion can never rot as new
    tape lands. Returns {leg: iso-string}; {} when nothing is readable. Best-effort: any
    exception yields {} so it can never poison the gate.

    `exclude_burst_windows` (default True, L269) drops captures that fall inside a DECLARED,
    padded burst-trigger window FOR THAT FAMILY — per-family, never global wall-clock, so a
    capture in a family no trigger covers still counts at the same instant. A burst pass is
    sanctioned re-collection, not a scheduled cron pass, and letting one stand in for a
    scheduled pass understates a real outage (measured 2.6x). Pass False to reproduce the
    pre-L269 reading. `stats` (optional out-dict, mutated in place) reports the exclusion so it
    is visible rather than silent: `n_burst_excluded`, `burst_excluded_by_family`,
    `scan_oldest_day` (the oldest day-file actually read — see L271: the horizon is newest-N
    day-FILES *per family*, i.e. ragged, so the aggregate max can be OLDER than the leg's true
    last capture), and `burst_table_unavailable` (families that degraded)."""
    out: Dict[str, str] = {}
    excluded: Dict[str, int] = {}
    degraded: List[str] = []
    oldest_day: Optional[date] = None
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
            windows = None
            if exclude_burst_windows:
                windows = _family_burst_windows(tgm, family)
                if windows is None:
                    degraded.append(family)
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
            for day, path in sorted(days)[-lookback_days:]:
                if oldest_day is None or day < oldest_day:
                    oldest_day = day
                try:
                    blob = path.read_bytes()
                except Exception:
                    continue
                for raw in set(_CAPTURED_AT_RE.findall(blob)):
                    ts = raw.decode("utf-8", "replace")
                    dt = _parse_capture_ts(ts)
                    if dt is None:
                        continue
                    if windows and any(lo <= dt <= hi for lo, hi in windows):
                        excluded[family] = excluded.get(family, 0) + 1
                        continue
                    leg = tgm.collector_bucket(dt)
                    if ts > out.get(leg, ""):
                        out[leg] = ts
        return out
    except Exception:
        return {}
    finally:
        if stats is not None:
            stats["exclude_burst_windows"] = bool(exclude_burst_windows)
            stats["burst_excluded_by_family"] = dict(excluded)
            stats["n_burst_excluded"] = sum(excluded.values())
            stats["scan_oldest_day"] = oldest_day.isoformat() if oldest_day else None
            stats["burst_table_unavailable"] = sorted(degraded)


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
                                  max_day: Optional[date] = None,
                                  exclude_burst_windows: bool = True,
                                  ) -> Optional[Dict[str, object]]:
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
        scan_stats: Dict[str, Any] = {}
        last_seen = _collector_leg_last_seen(tape_root, lookback_days=lookback_days,
                                             max_day=max_day,
                                             exclude_burst_windows=exclude_burst_windows,
                                             stats=scan_stats)
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
            # L269 provenance: what the reading EXCLUDED and how far back it could see.
            "exclude_burst_windows": scan_stats.get("exclude_burst_windows"),
            "n_burst_excluded": scan_stats.get("n_burst_excluded"),
            "burst_excluded_by_family": scan_stats.get("burst_excluded_by_family"),
            "burst_table_unavailable": scan_stats.get("burst_table_unavailable"),
            "scan_oldest_day": scan_stats.get("scan_oldest_day"),
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

    def _burst_and_horizon_lines() -> List[str]:
        """L269 provenance lines. Kept OPTIONAL — a diag dict built before these keys existed
        (or by a test fixture) renders exactly as it used to, no KeyError, no invented number."""
        out: List[str] = []
        n = diag.get("n_burst_excluded")
        if diag.get("exclude_burst_windows") and isinstance(n, int):
            by_fam = diag.get("burst_excluded_by_family") or {}
            fams = ", ".join(sorted(by_fam)) if isinstance(by_fam, dict) and by_fam else "none"
            out.append(
                f"  - excluded from this reading: {n} capture(s) written inside a DECLARED "
                f"burst-trigger window (families: {fams}). A burst is sanctioned extra "
                f"collection, not a scheduled pass; counting one as a scheduled pass used to "
                f"make a dead leg look days fresher than it was (see kb/lessons L269).")
        unavailable = diag.get("burst_table_unavailable")
        if unavailable:
            out.append(
                f"  - NOTE: the burst-window table could not be read for "
                f"{', '.join(unavailable)} — those families were counted WITHOUT the "
                f"exclusion, so this reading may still be optimistic.")
        oldest = diag.get("scan_oldest_day")
        if oldest:
            out.append(
                f"  - horizon caveat: the scan reads the newest {lookback} DAY-FILES PER "
                f"FAMILY, which is a ragged window, not {lookback} calendar days — a family "
                f"that writes a file most days reaches back ~{lookback} days, a sparse one "
                f"reaches back much further (oldest day read here: {oldest}). So this "
                f"last-capture date is the newest non-burst capture VISIBLE IN THAT WINDOW and "
                f"can be OLDER than the leg's true last capture; treat the exact date as "
                f"indicative and the 'is it dead' verdict as the reliable part.")
        return out

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
        lines += _burst_and_horizon_lines()
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
    ] + _burst_and_horizon_lines() + [
        "  " + tail,
    ])


# ─── Hollow crypto-ladder advisory (L168/L169: non-gating, offline-safe) ────────

# 2026-07-26 finding (tape-auditor + verifier, two-agent-confirmed):
# `tape/orderbook_depth/` can produce a record that is present, well-formed, and tagged
# `real_ask`/`real_bid` yet completely HOLLOW (`yes_bids=[]`, `no_bids=[]`, `depth=0`) because
# the fetch reached its ticker after that ticker's own close time. `completeness_ok` (computed
# in collection/orderbook_depth.py, never persisted to the tape line) cannot see this — a
# 200-OK empty book is not a fetch failure. `scripts/orderbook_depth_hollow_ladder_audit.py`
# is the read-only reproducer; this advisory surfaces its per-day crypto hollow rate so a run
# with 0 usable crypto ladders for a whole day (verified real: 2026-07-23, 2026-07-25) is
# visible in the one place every run is required to read, not just in a findings/ doc nobody
# re-opens. Non-gating: the mechanism is a pass-duration/discovery-timing issue outside this
# script's control, not a data-integrity violation, and a legitimate deep-OTM wing can also be
# empty (L23) — this is a rate signal for a human to watch, not a correctness assert.
HOLLOW_CRYPTO_DAY_LOOKBACK = 10
HOLLOW_CRYPTO_ALERT_FRACTION = 0.5  # a day where >=50% of that day's crypto records are hollow
_ORDERBOOK_DEPTH_HOLLOW_AUDIT_PATH = ROOT / "scripts" / "orderbook_depth_hollow_ladder_audit.py"


def _load_orderbook_depth_hollow_audit(path: Path = _ORDERBOOK_DEPTH_HOLLOW_AUDIT_PATH):
    """Import scripts/orderbook_depth_hollow_ladder_audit.py by path (scripts/ is not a
    package). Returns None on ANY failure so this advisory can never poison the gate."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_inv_odh_audit", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _hollow_crypto_ladder_issues(tape_root: Path = ROOT / "tape",
                                 lookback_days: int = HOLLOW_CRYPTO_DAY_LOOKBACK,
                                 max_day: Optional[date] = None
                                 ) -> List[Dict[str, object]]:
    """Per-day crypto hollow-ladder rate over the most recent `lookback_days` committed
    `tape/orderbook_depth/dt=*.jsonl` files, restricted to days at/above
    `HOLLOW_CRYPTO_ALERT_FRACTION`. Read-only, no network. Best-effort: any exception yields [].

    `max_day` (optional) restricts the scan to `dt=<date>.jsonl` files on or before that day —
    same convention as `_collector_leg_last_seen`'s own `max_day`, so a test pinning a real-tape
    day-set can freeze the "most recent lookback_days" window and never rot as new tape lands
    (L140's time-bomb discipline)."""
    try:
        mod = _load_orderbook_depth_hollow_audit()
        if mod is None:
            return []
        family_dir = tape_root / "orderbook_depth"
        if not family_dir.is_dir():
            return []
        candidates = sorted(family_dir.glob("dt=*.jsonl"))
        if max_day is not None:
            candidates = [p for p in candidates
                          if p.stem.split("=", 1)[1] <= max_day.isoformat()]
        wanted_days = {p.stem.split("=", 1)[1] for p in candidates[-lookback_days:]}
        if not wanted_days:
            return []
        records, _ = mod.load_records(family_dir)  # one pass over the directory, not one per day
        by_day: Dict[str, Dict[str, int]] = {}
        for rec in records:
            day = rec["_day"]
            if day not in wanted_days or not mod.is_crypto_ticker(rec.get("ticker", "")):
                continue
            bucket = by_day.setdefault(day, {"total": 0, "hollow": 0})
            bucket["total"] += 1
            bucket["hollow"] += mod.is_hollow(rec)
        issues: List[Dict[str, object]] = []
        for day in sorted(wanted_days):
            bucket = by_day.get(day)
            if not bucket or not bucket["total"]:
                continue
            frac = bucket["hollow"] / bucket["total"]
            if frac >= HOLLOW_CRYPTO_ALERT_FRACTION:
                issues.append({"day": day, "crypto_total": bucket["total"],
                               "crypto_hollow": bucket["hollow"], "fraction": frac})
        return issues
    except Exception:
        return []


def hollow_crypto_ladder_warning(issues: List[Dict[str, object]]) -> Optional[str]:
    """A non-gating advisory naming any recent day where a large share of
    `tape/orderbook_depth/`'s crypto records are hollow (empty book, fetched post-close or
    mid-overrun). Pure. NEVER flips the exit code. See kb/lessons/00-lessons.md L168/L169."""
    if not issues:
        return None
    lines = [f"warning (non-gating): {len(issues)} day(s) in "
             f"tape/orderbook_depth/ have >= {HOLLOW_CRYPTO_ALERT_FRACTION:.0%} of their crypto "
             f"(KXBTC/KXETH) records HOLLOW (empty book, depth=0) — a 200-OK fetch that reached "
             f"its ticker after close, not a collector failure `completeness_ok` can see:"]
    for issue in issues:
        lines.append(f"  - dt={issue['day']}: {issue['crypto_hollow']}/{issue['crypto_total']} "
                     f"crypto records hollow ({issue['fraction']:.0%})")
    lines.append("  Computed from committed tape only via "
                 "scripts/orderbook_depth_hollow_ladder_audit.py. Advisory only — does NOT "
                 "affect the exit code. See kb/lessons/00-lessons.md L168/L169.")
    return "\n".join(lines)


# ─── Capped-pagination span-vs-cadence advisory (L185: non-gating) ─────────────
#
# L185: a capped, newest-first-paginated harvest with NO time-window request parameter has a
# coverage ceiling of `cap / event_rate`, independent of how often the leg fires — and it does
# NOT improve as the ledger accumulates days (each pass just restarts the cursor from "now").
# `collection/settlement_ledger.py` is the worked example: 5000 rows/pass, no min_close_ts /
# max_close_ts, once a day, reaching back only ~1.3-3.8h of close_time against a 24h interval.
# Every existing cadence detector reads this family GREEN while that hole is wide open.
#
# NON-GATING, deliberately: a cap/window mismatch is a collector DESIGN property. Fixing it
# means changing the request shape (or the cadence) and re-collecting — nothing a cloud research
# run can repair mid-loop, and the condition is true of every committed pass ever written, so
# gating would halt the loop indefinitely over an unfixable state. Same posture as the
# hollow-ladder and dead-collector-leg advisories: it PRINTS to stderr, it never flips the exit
# code.
#
# Single source of truth: `CAPPED_PAGINATION_FAMILIES` and the check itself are IMPORTED from
# scripts/tape_gap_monitor.py via `_load_tape_gap_monitor`, never re-declared here — a second
# copy of the cadence/cap/threshold table would drift the moment either is recalibrated (the
# duplication trap L100 collapsed out of the collectors).


def _capped_pagination_span_issues(tape_root: Path = ROOT / "tape"
                                   ) -> List[Dict[str, object]]:
    """One issue dict per registered family with >=1 NARROW capture (event-time span far below
    the leg's firing interval), computed from committed tape only — read-only, no network.
    Best-effort: any exception yields [], so it can never poison the gate."""
    try:
        tgm = _load_tape_gap_monitor()
        if tgm is None or not tape_root.is_dir():
            return []
        issues: List[Dict[str, object]] = []
        for family in sorted(getattr(tgm, "CAPPED_PAGINATION_FAMILIES", {})):
            cov = tgm.capped_pagination_span_coverage(tape_root, family)
            if not cov or not cov.get("n_captures_narrow"):
                continue
            issues.append({
                "family": family,
                "cadence_hours": cov["cadence_hours"],
                "cap": cov["cap"],
                "time_key": cov["time_key"],
                "n_captures": cov["n_captures"],
                "n_captures_judged": cov["n_captures_judged"],
                "n_captures_not_judged": cov["n_captures_not_judged"],
                "n_captures_narrow": cov["n_captures_narrow"],
                "narrow_captures": cov["narrow_captures"],
            })
        return issues
    except Exception:
        return []


def capped_pagination_span_warning(issues: List[Dict[str, object]]) -> Optional[str]:
    """A non-gating advisory naming any capped-pagination family whose per-pass captured
    event-time window is far narrower than its own firing interval (L185). Pure. NEVER flips
    the exit code. See kb/lessons/00-lessons.md L185."""
    if not issues:
        return None
    lines = [f"warning (non-gating): {len(issues)} capped-pagination collector family(ies) "
             f"capture a per-pass event-time window far NARROWER than their firing interval "
             f"— a `cap / event_rate` coverage ceiling that MORE DAYS CANNOT FIX (L185):"]
    for issue in issues:
        narrow = issue["narrow_captures"] or []
        lines.append(
            f"  - {issue['family']}: cap={issue['cap']} rows/pass, no time-window parameter, "
            f"fires every {float(issue['cadence_hours']):.0f}h; "
            f"{issue['n_captures_narrow']}/{issue['n_captures_judged']} judged capture(s) narrow "
            f"({issue['n_captures_not_judged']} not judged — too few rows / no parseable "
            f"{issue['time_key']}, reported, never assumed ok)")
        for cap_rec in narrow:
            rph = cap_rec.get("rows_per_hour")
            rph_s = f"{rph:.0f} rows/h" if isinstance(rph, (int, float)) else "rows/h undefined"
            lines.append(
                f"      {cap_rec['capture_id']}: {cap_rec['n_rows_with_time']} rows spanning "
                f"{cap_rec['span_hours']:.2f}h of {issue['time_key']} ({rph_s}) => coverage "
                f"ceiling {float(cap_rec['coverage_ceiling_fraction']):.1%} of the "
                f"{float(issue['cadence_hours']):.0f}h interval")
    lines.append("  Computed from committed tape only via "
                 "scripts/tape_gap_monitor.py::capped_pagination_span_coverage. Advisory only "
                 "— does NOT affect the exit code. See kb/lessons/00-lessons.md L185.")
    return "\n".join(lines)


def _completeness_cap_saturation_issues(tape_root: Path = ROOT / "tape"
                                        ) -> List[Dict[str, object]]:
    """One issue dict per registered family whose measured at-cap fraction clears the
    saturation alert threshold, computed from committed tape only -- read-only, no network.
    Best-effort: any exception yields [], so it can never poison the gate."""
    try:
        tgm = _load_tape_gap_monitor()
        if tgm is None or not tape_root.is_dir():
            return []
        issues: List[Dict[str, object]] = []
        for family in sorted(getattr(tgm, "COMPLETENESS_CAP_FAMILIES", {})):
            cov = tgm.completeness_cap_saturation(tape_root, family)
            if not cov or not cov.get("saturated"):
                continue
            issues.append(cov)
        return issues
    except Exception:
        return []


def completeness_cap_saturation_warning(issues: List[Dict[str, object]]) -> Optional[str]:
    """A non-gating advisory naming any bounded-collector family whose committed
    `completeness_ok` signal is STRUCTURALLY saturated -- (nearly) every real pass hits the
    collector's own page cap, so `hourly_pass`'s completeness AND (and the VPS pager it
    drives) fires on a permanent, already-known cap-vs-universe fact rather than a new
    failure (L270). Pure. NEVER flips the exit code. See kb/lessons/00-lessons.md L270."""
    if not issues:
        return None
    lines = [f"warning (non-gating): {len(issues)} bounded-collector family(ies) have a "
             f"STRUCTURALLY SATURATED completeness_ok signal -- hourly_pass's completeness "
             f"AND (and the VPS pager it drives) fires on a permanent cap-vs-universe fact, "
             f"not a new failure (L270):"]
    for issue in issues:
        lines.append(f"  - {issue['family']}: {issue['n_at_cap']}/{issue['n_captures']} "
                     f"committed captures ({float(issue['fraction_at_cap']):.0%}) sit "
                     f"EXACTLY at the collector's own cap ({issue['cap']} rows/pass)")
    lines.append("  Computed from committed tape only via "
                 "scripts/tape_gap_monitor.py::completeness_cap_saturation. Advisory only "
                 "-- does NOT affect the exit code. See kb/lessons/00-lessons.md L270.")
    return "\n".join(lines)


# ─── Expected-window-grid coverage advisory (L208: non-gating) ─────────────────
#
# L208: a per-window density statistic built only from windows that produced >=1 observation
# is a SURVIVORSHIP statistic. A window the collector never fired in cannot enter it, so the
# metric reads healthiest exactly where coverage is worst — `q42_funding_estimate_path_
# inference.py`'s "median 2.0 samples/window" over `tape/perp_tape/` is the worked example.
#
# The honest denominator is the EXPECTED window grid, anchored on the COLLECTOR'S OWN
# boundary field. That anchor is load-bearing: the audit that first reported this defect
# binned `captured_at` into 00Z-anchored 8h calendar bins, while the funding boundaries in
# `next_funding_time` are on the 04/12/20Z grid — the two disagree about which windows are
# empty (see findings/2026-07-30-l208-window-grid-coverage.md).
#
# NON-GATING: a zero-capture window is a permanently unrecoverable historical fact (the
# collector destroys the premium path at each boundary with no re-fetch), so gating would
# halt the loop forever over the past. Same posture as the hollow-ladder / capped-pagination
# / colliding-capture_id advisories.
#
# Single source of truth: `WINDOW_GRIDDED_FAMILIES` and the computation are IMPORTED from
# scripts/tape_gap_monitor.py, never re-declared here (the L100 duplication trap).


def _window_grid_coverage_issues(tape_root: Path = ROOT / "tape") -> List[Dict[str, object]]:
    """One issue dict per registered window-gridded family with >=1 zero-capture window OR
    >=1 off-grid window key, computed from committed tape only — read-only, no network.
    Best-effort: any exception yields [], so it can never poison the gate."""
    try:
        tgm = _load_tape_gap_monitor()
        if tgm is None or not tape_root.is_dir():
            return []
        issues: List[Dict[str, object]] = []
        for family in sorted(getattr(tgm, "WINDOW_GRIDDED_FAMILIES", {})):
            cov = tgm.expected_window_grid_coverage(tape_root, family)
            if not cov:
                continue
            if not cov.get("n_windows_zero_capture") and not cov.get("n_offgrid_window_keys"):
                continue
            issues.append(cov)
        return issues
    except Exception:
        return []


def window_grid_coverage_warning(issues: List[Dict[str, object]]) -> Optional[str]:
    """A non-gating advisory naming any window-gridded family whose EXPECTED window grid has
    windows with zero capture passes (invisible to any observed-windows-only density
    statistic, L208), or window keys off its configured grid. Pure. NEVER flips the exit
    code. See kb/lessons/00-lessons.md L208."""
    if not issues:
        return None
    lines = [f"warning (non-gating): {len(issues)} window-gridded tape family(ies) have "
             f"EXPECTED windows with ZERO capture passes — structurally invisible to any "
             f"per-window density statistic computed over OBSERVED windows only (L208):"]
    for cov in issues:
        zero = list(cov.get("zero_capture_windows") or [])
        obs = cov.get("observed_only") or {}
        filled = cov.get("grid_filled") or {}
        lines.append(
            f"  - {cov['family']}: grid = {cov['window_key']} every "
            f"{float(cov['window_hours']):.0f}h anchored {int(cov['anchor_hour_utc']):02d}Z, "
            f"{cov['grid_start']} -> {cov['grid_end']}; "
            f"{cov['n_windows_observed']}/{cov['n_windows_expected']} windows observed "
            f"=> {cov['n_windows_zero_capture']} with ZERO passes, "
            f"{cov['n_windows_thin']} at or below {cov['thin_max_passes']} pass(es) "
            f"({float(cov['path_inadequate_fraction']):.1%} path-inadequate)")
        lines.append(
            f"      passes/window: observed-only median={obs.get('median_passes')} "
            f"min={obs.get('min_passes')} | grid-filled median={filled.get('median_passes')} "
            f"min={filled.get('min_passes')} (the survivorship gap L208 names)")
        for w in zero[:5]:
            lines.append(f"      ZERO-pass window: {w}")
        if len(zero) > 5:
            lines.append(f"      ... and {len(zero) - 5} more zero-pass window(s)")
        if cov.get("n_offgrid_window_keys"):
            lines.append(
                f"      {cov['n_offgrid_window_keys']} OFF-GRID {cov['window_key']} value(s) "
                f"reported, never snapped (e.g. {', '.join(cov.get('offgrid_examples') or [])}) "
                f"— the venue's cadence may have changed; re-read the anchor before trusting "
                f"any window statistic on this family")
        if cov.get("n_rows_skipped_no_window_key"):
            lines.append(f"      {cov['n_rows_skipped_no_window_key']} row(s) skipped with no "
                         f"parseable {cov['window_key']} (reported, never bucketed)")
    lines.append("  Density unit is the distinct capture pass (`capture_id`); a second-"
                 "granularity collision (L210) reads LOW here, i.e. toward flagging, never "
                 "toward a false all-clear. Computed from committed tape only via "
                 "scripts/tape_gap_monitor.py::expected_window_grid_coverage. Advisory only "
                 "— does NOT affect the exit code. See kb/lessons/00-lessons.md L208.")
    return "\n".join(lines)


# ─── Colliding-capture_id advisory (L210: non-gating, offline-safe) ────────────

# `capture_id` is a second-granularity pass LABEL, not a unique capture key: two DISTINCT
# collector invocations that start inside the same wall-clock second share one id, and any
# consumer that groups or de-duplicates by it then merges two different payloads into one
# "pass". `scripts/tape_gap_monitor.py::aggregate_family` is itself such a consumer, so its
# UNDER-CAPTURE pass ratio undercounts by exactly the collision count.
#
# The detector deliberately does NOT flag "one capture_id with several captured_at" — that
# is the BENIGN shape of a ladder/burst round walking many strikes (hf_burst). It flags only
# a REPEATED LOGICAL ITEM under one capture_id, and structurally exempts any family that
# stamps its own within-pass sequence field. See tape_gap_monitor for the full argument.
#
# Non-gating: these are historical properties of already-committed append-only tape that no
# run can retroactively repair, so gating would halt the loop indefinitely over a fact.
#
# Single source of truth: the check and its field tables are IMPORTED from
# scripts/tape_gap_monitor.py via `_load_tape_gap_monitor`, never re-declared here (L100).


def _duplicate_capture_id_issues(tape_root: Path = ROOT / "tape"
                                 ) -> List[Dict[str, object]]:
    """One issue dict per tape family with >=1 capture_id under which the SAME logical item
    was written twice (two invocations sharing a second-granularity id, L210). Computed from
    committed tape only — read-only, no network. Best-effort: any exception yields [], so it
    can never poison the gate."""
    try:
        tgm = _load_tape_gap_monitor()
        if tgm is None or not tape_root.is_dir():
            return []
        candidates = tgm._collision_candidate_families(tape_root)
        issues: List[Dict[str, object]] = []
        for family in sorted(candidates):
            res = tgm.duplicate_capture_id_collisions(tape_root, family, candidates[family])
            if not res or not res.get("n_collisions"):
                continue
            issues.append({
                "family": family,
                "n_candidate_capture_ids": res["n_candidate_capture_ids"],
                "n_collisions": res["n_collisions"],
                "collisions": res["collisions"],
            })
        return issues
    except Exception:
        return []


def duplicate_capture_id_warning(issues: List[Dict[str, object]]) -> Optional[str]:
    """A non-gating advisory naming every tape family whose `capture_id` is not a unique
    join key — the same logical item written twice under one id by two distinct collector
    invocations (L210). Pure. NEVER flips the exit code. See kb/lessons/00-lessons.md L210."""
    if not issues:
        return None
    total = sum(int(i["n_collisions"]) for i in issues)
    lines = [f"warning (non-gating): {total} colliding `capture_id` group(s) across "
             f"{len(issues)} tape family(ies) — the SAME logical item written more than once "
             f"under ONE second-granularity capture_id, i.e. two distinct collector "
             f"invocations merged into one apparent pass (L210). Any consumer that groups or "
             f"de-duplicates by `capture_id` (including tape_gap_monitor's own UNDER-CAPTURE "
             f"pass ratio) undercounts passes and double-counts payload here:"]
    for issue in issues:
        lines.append(f"  - {issue['family']}: {issue['n_collisions']} collided item(s) over "
                     f"{issue['n_candidate_capture_ids']} candidate capture_id(s)")
        for col in list(issue["collisions"])[:3]:
            key = ", ".join(f"{k}={v}" for k, v in col["item_key"]) or "<pass-summary row>"
            diff = sorted(col["differing_fields"]) or ["<none — byte-identical payload>"]
            lines.append(f"      {col['capture_id']} [{key}]: "
                         f"{col['n_distinct_captured_at']} distinct captured_at; "
                         f"differing field(s): {', '.join(str(d) for d in diff[:6])}")
    lines.append("  Benign ladder/burst rounds are NOT flagged: a family stamping its own "
                 "within-pass sequence field (capture_seq/capture_mono_ns/round_index) is "
                 "structurally exempt, so hf_burst's 10-strike round reads clean. Computed "
                 "from committed tape only via scripts/tape_gap_monitor.py::"
                 "duplicate_capture_id_collisions. Advisory only — does NOT affect the exit "
                 "code. See kb/lessons/00-lessons.md L210.")
    return "\n".join(lines)


# ─── Econ-print settlement-status regression advisory (L223: non-gating, offline-safe) ──
#
# L223: `collection/econ_prints.py::fetch_recent_settlement` treats `no_settled_events` as a
# valid, non-error status (`pass_complete` counts it as OK) — correct for a series that has
# never settled anything, but the SAME status also fires once a series' settled-events query
# stops finding an event it previously found. Real-tape instance: the `gdp` leg reported one
# real settlement (`KXGDP-26APR30`, 2026-07-05) then `no_settled_events` on all 340+ passes
# through 2026-07-29 while `pass_complete: true` held throughout — a silent 23+ day regression
# that reads identically to "this series never had a settlement." This advisory is a
# TAPE-LEVEL detector (reads committed tape only, never touches the collector): for each
# `series_key`, once a `settled` status has been observed, any LATER run of
# `ECON_PRINTS_REGRESSION_MIN_STREAK`-or-more consecutive `no_settled_events` captures for that
# same key is flagged. NON-GATING: the fix (a collector/upstream-API change) is nothing a
# cloud run can make mid-loop, and the condition, once true, stays true on every future pass
# until a human repairs it — gating would halt the loop indefinitely over an unfixable state.

ECON_PRINTS_REGRESSION_MIN_STREAK = 3


def _econ_prints_settlement_regression_issues(
        tape_root: Path = ROOT / "tape",
        min_streak: int = ECON_PRINTS_REGRESSION_MIN_STREAK) -> List[Dict[str, object]]:
    """Per `series_key` in `tape/econ_prints/`, detect a `recent_settlement.status`
    regression from `settled` back to `no_settled_events` sustained for >= `min_streak`
    consecutive captures (lesson L223). Read-only, offline, chronological over committed
    `dt=<date>.jsonl` files (append-only within each file, files sorted by name so days are
    read in order). Best-effort: any exception (missing dir, malformed line, absent field) is
    swallowed and skips just that line/family, never poisoning the gate."""
    family_dir = tape_root / "econ_prints"
    if not family_dir.is_dir():
        return []
    by_key: Dict[str, List[Tuple[str, str, Optional[str]]]] = {}
    for path in sorted(family_dir.glob("dt=*.jsonl")):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    key = rec.get("series_key")
                    rs = rec.get("recent_settlement")
                    if not key or not isinstance(rs, dict):
                        continue
                    status = rs.get("status")
                    if status not in ("settled", "no_settled_events"):
                        continue
                    by_key.setdefault(key, []).append(
                        (rec.get("captured_at", ""), status, rs.get("event_ticker")))
        except Exception:
            continue
    issues: List[Dict[str, object]] = []
    for key, seq in by_key.items():
        seen_settled: Optional[str] = None
        streak = 0
        streak_start: Optional[str] = None
        for captured_at, status, event_ticker in seq:
            if status == "settled":
                seen_settled = event_ticker
                streak = 0
                streak_start = None
            else:  # no_settled_events
                if seen_settled is None:
                    continue  # never settled — the normal, non-regressed case
                if streak == 0:
                    streak_start = captured_at
                streak += 1
        if seen_settled is not None and streak >= min_streak:
            issues.append({
                "series_key": key,
                "last_settled_event_ticker": seen_settled,
                "streak": streak,
                "regression_since": streak_start,
            })
    return sorted(issues, key=lambda i: i["series_key"])


def econ_prints_settlement_regression_warning(issues: List[Dict[str, object]]) -> Optional[str]:
    """A non-gating advisory naming any `tape/econ_prints/` series_key whose most recent
    settlement went from a real `settled` value back to `no_settled_events` for
    `ECON_PRINTS_REGRESSION_MIN_STREAK`-or-more consecutive passes. Pure. NEVER flips the exit
    code. See kb/lessons/00-lessons.md L223."""
    if not issues:
        return None
    lines = [f"warning (non-gating): {len(issues)} tape/econ_prints/ series_key(s) regressed "
             f"from a real settlement back to `no_settled_events` — a status the collector "
             f"treats as OK (`pass_complete` stays true) but that is indistinguishable here "
             f"from a silent loss of a real settled event:"]
    for issue in issues:
        lines.append(f"  - {issue['series_key']}: last real settlement "
                     f"{issue['last_settled_event_ticker']}, then {issue['streak']} "
                     f"consecutive no_settled_events pass(es) since {issue['regression_since']}")
    lines.append("  Computed from committed tape only. Advisory only — does NOT affect the "
                 "exit code. See kb/lessons/00-lessons.md L223.")
    return "\n".join(lines)


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


# ─── scripts/ cross-import sys.path bootstrap advisory (L232 residue: non-gating, offline) ──
#
# L232's rule: a file under `scripts/` that imports from the `scripts.` PACKAGE must carry a
# repo-root `sys.path` bootstrap AHEAD of that import. `pyproject.toml` installs
# core/collection/validation/analysis as packages but NOT `scripts`, and the repo-root
# `conftest.py` repairs `sys.path` only under pytest — so a missing bootstrap breaks exactly
# the `python3 scripts/foo.py` invocation form that kb/, findings/ and LOOP-QUEUE.md cite,
# while every in-process import test stays green.

# A bootstrap argument whose source segment ENDS in a `"scripts"` string literal inserts the
# scripts DIRECTORY, which makes `import foo` work but NOT `import scripts.foo` — the
# `scripts/gen_problems_dashboard.py` shape. It must not count as a bootstrap for this rule.
_SCRIPTS_DIR_LITERAL_RE = re.compile(r"""["']scripts["']\s*\)*\s*$""")


def _imports_scripts_package(node: ast.AST) -> bool:
    """True if `node` is a REAL import statement pulling in the `scripts` package.

    `ast.ImportFrom(level=0, module='scripts'|'scripts.x')` or `ast.Import` naming
    `scripts`/`scripts.x`. A relative import (`level > 0`) is a different mechanism and is not
    flagged. Pure; no filesystem access."""
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        return (node.level or 0) == 0 and (mod == "scripts" or mod.startswith("scripts."))
    if isinstance(node, ast.Import):
        return any(a.name == "scripts" or a.name.startswith("scripts.") for a in node.names)
    return False


def _sys_path_bootstrap_linenos(tree: ast.AST, source: str) -> List[int]:
    """Line numbers of `sys.path.insert(...)` / `sys.path.append(...)` calls that plausibly put
    the REPO ROOT on `sys.path`. Calls whose inserted path is the `scripts` directory itself are
    excluded (see `_SCRIPTS_DIR_LITERAL_RE`). Lexical proxy on the argument's source segment —
    a variable it cannot resolve is accepted permissively (a MISS, not a false alarm)."""
    out: List[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr in ("insert", "append")):
            continue
        base = fn.value
        if not (isinstance(base, ast.Attribute) and base.attr == "path"
                and isinstance(base.value, ast.Name) and base.value.id == "sys"):
            continue
        arg = node.args[-1] if node.args else None
        seg = ""
        if arg is not None:
            try:
                seg = ast.get_source_segment(source, arg) or ""
            except Exception:
                seg = ""
        if seg and _SCRIPTS_DIR_LITERAL_RE.search(seg.strip()):
            continue
        out.append(node.lineno)
    return sorted(out)


def _scripts_cross_import_bootstrap_issues(root: Path = ROOT) -> List[str]:
    """Files under `scripts/` that import the `scripts.` package with no repo-root `sys.path`
    bootstrap ahead of that import (L232). Returns sorted `scripts/foo.py:LINENO` labels naming
    the FIRST offending import in each file.

    AST-based on purpose: a line-level regex has a demonstrated false positive on
    `scripts/q48_s55_fomc_lag_probe.py`, whose module DOCSTRING contains a
    `from scripts.q48_s55_fomc_lag_probe import ...` usage example. The AST also reaches
    FUNCTION-LOCAL imports (`scripts/q35_maker_rebate_reframe.py`,
    `scripts/q39_graveyard_counterfactual_sweep.py`), which a "first import line" heuristic
    would miss.

    Best-effort/offline: an unreadable file or a SyntaxError skips that file and can never
    poison the gate."""
    out: List[str] = []
    try:
        scripts_dir = root / "scripts"
        if not scripts_dir.is_dir():
            return []
        for p in sorted(scripts_dir.rglob("*.py")):
            if _excluded_relative_to(root, p):
                continue
            try:
                source = p.read_text()
                tree = ast.parse(source)
            except Exception:
                continue
            imports = [n.lineno for n in ast.walk(tree) if _imports_scripts_package(n)]
            if not imports:
                continue
            first = min(imports)
            boots = _sys_path_bootstrap_linenos(tree, source)
            if any(b < first for b in boots):
                continue
            rel = str(p.resolve().relative_to(root.resolve())).replace("\\", "/")
            out.append(f"{rel}:{first}")
        return sorted(out)
    except Exception:
        return []


def scripts_cross_import_bootstrap_warning(sites: List[str]) -> Optional[str]:
    """Non-gating advisory when a file under `scripts/` imports the `scripts.` package without a
    repo-root `sys.path` bootstrap ahead of it, else None. Pure.

    States the TESTED shapes and the KNOWN BLIND SPOTS, not the intent: this is a static proxy,
    and reporting 0 sites is evidence of PRECISION only, never of RECALL (L155)."""
    if not sites:
        return None
    n = len(sites)
    examples = ", ".join(sites[:3]) + (", ..." if n > 3 else "")
    return (
        f"warning (non-gating): {n} file(s) under `scripts/` import the `scripts.` package with "
        f"no repo-root `sys.path` bootstrap ahead of the import (e.g. {examples}). "
        f"`pyproject.toml` does NOT install `scripts` as a package and the repo-root "
        f"`conftest.py` repairs `sys.path` only under pytest, so `python3 scripts/foo.py` — the "
        f"invocation form kb/, findings/ and LOOP-QUEUE.md cite — dies with "
        f"`ModuleNotFoundError: No module named 'scripts'` while every in-process import test "
        f"stays green (L232). Fix: "
        f"`sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` above the import, the "
        f"`scripts/q48_s55_fomc_lag_probe.py` pattern, pinned by a REAL SUBPROCESS test with "
        f"`PYTHONPATH` scrubbed and cwd outside the repo. "
        f"COVERAGE (tested shapes): module-level and function-local `from scripts.x import y` / "
        f"`from scripts import x` / `import scripts.x`; a bootstrap ANYWHERE at a lower line "
        f"number counts; a bootstrap inserting the `scripts` DIRECTORY (`ROOT / \"scripts\"`) "
        f"correctly does NOT count; a `from scripts.` inside a docstring or comment is NOT a "
        f"hit. KNOWN BLIND SPOTS (deliberate, regression-tested as misses): a bootstrap hidden "
        f"behind a helper call or an imported side-effect module, `sys.path` mutated by "
        f"`+=`/slice assignment/`extend`, an aliased `from sys import path`, a bootstrap whose "
        f"inserted path is an unresolvable variable (accepted permissively), a bootstrap that "
        f"sits at a lower LINE but inside a function that runs after the import, and dynamic "
        f"`importlib.import_module(\"scripts.x\")`. A 0-site report does NOT mean the tree is "
        f"clean. Advisory only — does NOT affect the exit code. "
        f"See kb/lessons/00-lessons.md L232."
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

# M1: a backticked `dir/file.py::symbol` (or `::Class.method`) inside an enforcement cell.
_PATH_SYMBOL_SPAN_RE = re.compile(
    r"^([A-Za-z0-9_][A-Za-z0-9_./-]*\.py)::"
    r"([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?$"
)
# M2: a backticked repo-relative `*.py` path, plus a backticked `--flag` token in the SAME cell.
_PY_PATH_SPAN_RE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_./-]*\.py)$")
_CLI_FLAG_RE = re.compile(r"--[A-Za-z][A-Za-z0-9-]*")
# M3: a backticked agent-charter path (the "encode it in the house style" enforcement family).
_AGENT_CHARTER_SPAN_RE = re.compile(r"^(\.claude/agents/[A-Za-z0-9_.-]+\.md)$")

# The formal supersession marker — see _lesson_disposed_ids' docstring for the exact grammar.
# `\bDISPOSES:` gives the token a LEFT word boundary (`XDISPOSES: L22` must not fire) and each
# ID carries a RIGHT one (`L22abc` is not `L22`) — both holes found by the 2026-07-27 verifier.
_DISPOSES_RE = re.compile(r"\bDISPOSES:\s*(L\d+\b(?:(?:\s*,\s*|[ \t]+)L\d+\b)*)")
_DISPOSES_ID_RE = re.compile(r"L\d+")

# The ledger's standing work-queue marker, as it is actually written (00-lessons.md line 9).
# BOTH shapes must be caught -- the 2026-07-27 verifier found L145 invisible to the old
# `startswith("**UNENFORCED**")` test because its em dash sits INSIDE the bold span:
#     **UNENFORCED** — candidate: ...
#     **UNENFORCED — UNRESOLVED COLLISION, flagged to parent/Ryan ...**
# i.e. a bold span whose FIRST WORD is UNENFORCED. Kept precise on purpose: the `\b` refuses
# `**UNENFORCEDISH**` / `**UNENFORCED_X**`, and anchoring at `^\*\*` refuses a mid-cell mention
# and the mixed-tier shape `**test (detection) + UNENFORCED (repair)**` (L168), whose enforced
# half is real. A bare unbolded `UNENFORCED ...` is likewise NOT the marker.
_UNENFORCED_MARKER_RE = re.compile(r"^\*\*UNENFORCED\b")

# L268 (2026-08-02): a row whose enforcement cell OPENS with a built tier but carries a
# bolded UNENFORCED token MID-CELL (the L168 shape: `**test (detection) + UNENFORCED
# (repair)**`) is invisible to `_UNENFORCED_MARKER_RE` -- the standing work queue is indexed
# by the cell's FIRST WORD only. `_BOLD_SPAN_RE` finds the FIRST `**...**` span only (the
# ledger's own tier-marker convention: every row's enforcement cell opens with one) -- scanning
# every bold span in the cell was tried first and measured 22 false positives on the real
# ledger, because a row that HAD an UNENFORCED marker and was later fully resolved routinely
# says so in its own (now single-tier) opening span, e.g. L47/L52's
# "**helper + test ... supersedes the earlier UNENFORCED marker per L152's own-row-update
# rule**" -- a closed row narrating its own history, not an open mixed-tier task. The word
# must be literally bold, not merely mentioned in prose after the bold span closes (L5/L7/L23/
# L90/L132/L133's `**test** ... UNENFORCED as a general invariant` shape is an honest terminal
# state, not a queued task), not inside a nested code span within the bold text (L123's
# `` `UNENFORCED` `` is a prose reference to the marker grammar itself, not a live marker), and
# not immediately followed by the word "marker" (the L47/L52 "the earlier UNENFORCED marker"
# retrospective-narration shape, the one false-positive class bolding alone did not filter).
_BOLD_SPAN_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_UNENFORCED_BOLD_WORD_RE = re.compile(r"\bUNENFORCED\b(?!\s+marker\b)")


def _mixed_tier_unenforced_ids(
    rows: List[Tuple[str, str, str]], disposed: Set[str]
) -> Tuple[str, ...]:
    """Lesson IDs (L268) whose ENFORCEMENT cell's FIRST bold span bolds the word UNENFORCED
    somewhere other than as the leading marker -- see `_BOLD_SPAN_RE`'s docstring comment above
    for the exact shape this catches and the false-positive shapes it deliberately excludes.
    Excludes any row already caught by `_UNENFORCED_MARKER_RE` (those are counted by
    `n_open_unenforced` already -- this field is additive, never a re-count) and any formally
    `DISPOSES:`-disposed id. Order follows the rows as parsed. Pure; never raises (a malformed
    or missing span is just not a match)."""
    ids: List[str] = []
    for lid, _lesson_text, enforcement in rows:
        if lid in disposed or _UNENFORCED_MARKER_RE.match(enforcement):
            continue
        m = _BOLD_SPAN_RE.search(enforcement)
        if m is None:
            continue
        span = _BACKTICK_SPAN_RE.sub("", m.group(1))
        if _UNENFORCED_BOLD_WORD_RE.search(span):
            ids.append(lid)
    return tuple(ids)


def _split_lesson_row(line: str) -> List[str]:
    """Split one markdown table row on its CELL delimiters only.

    `str.split("|")` is wrong for this ledger: 14 of the 190 rows on 2026-07-27 carry a pipe
    INSIDE a cell -- escaped (`\\|`, e.g. L145's `SIGNATURE\\|TIMESTAMP` header name) or inside a
    backticked code span (L161's `sed 's|refs/heads/||'`) -- so a naive split shifts every later
    column left and `cols[5]` silently becomes a FRAGMENT OF THE LESSON TEXT (measured: L25, L37,
    L62, L89, L109, L145, L147, L161, L173, L177, L179, L180, L183, L184). Two cells were then
    mis-read as enforcement, one of which (L145) hid a genuinely-open UNENFORCED row.

    `cols[-2]` is NOT a fix either: L147's own ENFORCEMENT cell contains the escaped pipe, so
    the last-but-one field is a tail fragment of that cell with its `**invariant ...**` tier
    marker cut off. Only a delimiter-aware split is correct for every row.

    Rules: a `\\|` is literal; a `|` inside a backtick span is literal; anything else delimits.
    Pure, never raises. Returns the raw (unstripped) fields, including the empty leading/trailing
    ones a well-formed row has."""
    fields: List[str] = []
    cur: List[str] = []
    in_code = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur.append("\\|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
            cur.append(ch)
            i += 1
            continue
        if ch == "|" and not in_code:
            fields.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    fields.append("".join(cur))
    return fields

# Matcher labels for the recall report (stable strings — tests and the advisory text use them).
STALE_MATCHERS = ("func", "path_symbol", "script_flag", "agent_charter")


def _parse_lesson_rows(
    lessons_path: Path = ROOT / "kb" / "lessons" / "00-lessons.md",
) -> List[Tuple[str, str, str]]:
    """(id, lesson_text, enforcement_text) for every table row in
    kb/lessons/00-lessons.md. Best-effort/offline: a read failure returns [].

    Cells are split by `_split_lesson_row` (escape- and code-span-aware) -- a naive
    `line.split("|")` mis-aligned 14 of the 190 rows on 2026-07-27, handing the detectors a
    fragment of the LESSON TEXT as the enforcement column. Any residual field beyond the
    canonical 5th column is re-joined rather than dropped: an unknown pipe shape must never
    TRUNCATE an enforcement cell, because its leading tier marker (`**UNENFORCED**`,
    `**test**`, ...) is exactly what every ledger detector keys on."""
    try:
        lines = lessons_path.read_text().splitlines()
    except Exception:
        return []
    rows: List[Tuple[str, str, str]] = []
    for line in lines:
        m = _LESSON_ID_ROW_RE.match(line)
        if not m:
            continue
        cols = _split_lesson_row(line)
        if len(cols) < 6:
            continue
        tail = cols[5:-1] if cols[-1].strip() == "" else cols[5:]
        rows.append((m.group(1), cols[3].strip(), "|".join(tail).strip()))
    return rows


def _lesson_disposed_ids(rows: List[Tuple[str, str, str]]) -> Set[str]:
    """Lesson IDs formally DISPOSED of by some row's ENFORCEMENT column, per the one canonical
    machine-readable supersession marker. A disposed ID is permanently skipped by
    `_stale_unenforced_candidate_issues` even if its own row still reads `**UNENFORCED**`.

    EXACT GRAMMAR (the kb-distiller writes this verbatim; nothing else suppresses a row):

        DISPOSES: L22, L27, L28

    - The literal, case-SENSITIVE token `DISPOSES:` (uppercase, immediately followed by a
      colon) appearing anywhere inside a row's ENFORCEMENT column -- the 5th pipe-delimited
      column. `disposes:`, `Disposes:` and a `DISPOSES:` in the lesson-text column do NOT count.
    - Then one or more lesson IDs of the form `L<digits>`, separated by a comma (with optional
      surrounding spaces) or by one or more spaces/tabs.
    - The list TERMINATES at the first thing that is not `<separator><L\\d+>`: end-of-cell, a
      period, semicolon, em dash, or any prose word. So
      `DISPOSES: L22, L27. Audited in findings/... which also revisits L39` disposes of
      exactly {L22, L27} -- the trailing prose mention of L39 does not join the list.
    - A bare prose mention of an ID anywhere ("see L22", "supersedes L22") NEVER suppresses;
      only the marker does. Several markers may appear in one cell / across several rows;
      their lists union.

    Best-effort: never raises. Pure over the already-parsed rows."""
    disposed: Set[str] = set()
    for _lesson_id, _lesson_text, enforcement in rows:
        for m in _DISPOSES_RE.finditer(enforcement):
            disposed.update(_DISPOSES_ID_RE.findall(m.group(1)))
    return disposed


def _safe_repo_path(source_root: Path, rel: str) -> Optional[Path]:
    """`source_root / rel` for a repo-relative token, or None if the token is absolute or
    escapes the root (`..`). Never touches the filesystem beyond the join."""
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return None
    return source_root / rel


def _extract_stale_candidates(enforcement: str) -> List[Tuple[str, Tuple[str, ...]]]:
    """(matcher, args) candidate tokens extracted from ONE enforcement cell. Pure lexical --
    no filesystem access, no judgement about whether the named artifact exists. See
    `_stale_unenforced_candidate_issues` for each matcher's rationale and blind spots."""
    spans = [s.strip() for s in _BACKTICK_SPAN_RE.findall(enforcement)]
    out: List[Tuple[str, Tuple[str, ...]]] = []
    seen: Set[Tuple[str, Tuple[str, ...]]] = set()

    def add(matcher: str, args: Tuple[str, ...]) -> None:
        key = (matcher, args)
        if key not in seen:
            seen.add(key)
            out.append(key)

    for span in spans:
        for fn in _FUNC_CALL_RE.findall(span):
            if "_" in fn:                                   # M0 (original matcher)
                add("func", (fn,))
        m = _PATH_SYMBOL_SPAN_RE.match(span)
        if m:                                               # M1
            add("path_symbol", (m.group(1), m.group(2), m.group(3) or ""))
        m = _AGENT_CHARTER_SPAN_RE.match(span)
        if m:                                               # M3
            add("agent_charter", (m.group(1),))
    py_paths = [s for s in spans if _PY_PATH_SPAN_RE.match(s)]
    flags = [f for s in spans for f in _CLI_FLAG_RE.findall(s)]
    for p in py_paths:                                      # M2 (same-cell path + flag)
        for f in flags:
            add("script_flag", (p, f))
    return out


def _resolve_stale_candidate(
    lesson_id: str,
    matcher: str,
    args: Tuple[str, ...],
    source_root: Path,
    func_defs: Dict[str, List[str]],
) -> List[str]:
    """Evidence strings for one candidate that RESOLVES to an artifact already in the tree
    (empty list if it does not). Reads files; never raises.

    WORDING CONTRACT (2026-07-27 verifier, L165 class): each string claims ONLY what the
    matcher actually showed -- the enforcement cell NAMES an artifact, and that artifact EXISTS
    in the tree. It must NOT claim the candidate is built/enforced: L76's cell backticks
    `tests/test_probe_ladder_coherence.py::test_runs_single_deep_snapshot_fails_duration_gate`,
    which exists, but that test asserts on snapshot COUNT (`MIN_SNAPS=2`) -- the very mechanism
    L76's lesson text says is NOT a wall-clock duration gate. A true hit, a NAME COINCIDENCE as
    evidence. Every string therefore ends in the "not proof it enforces <id>" qualifier."""
    try:
        if matcher == "func":
            fn = args[0]
            return [
                f"{lesson_id}: cell NAMES `{fn}()`, which is DEFINED in {f} "
                f"(name match only -- not proof it enforces {lesson_id})"
                for f in func_defs.get(fn, [])
            ]
        if matcher == "path_symbol":
            rel, sym, sub = args[0], args[1], args[2]
            p = _safe_repo_path(source_root, rel)
            if p is None or not p.is_file():
                return []
            text = p.read_text(errors="replace")
            if sub:
                ok = (re.search(rf"^\s*class\s+{re.escape(sym)}\s*[(:]", text, re.M) is not None
                      and re.search(rf"^\s*def\s+{re.escape(sub)}\s*\(", text, re.M) is not None)
                label = f"{rel}::{sym}.{sub}"
            else:
                ok = (re.search(rf"^\s*def\s+{re.escape(sym)}\s*\(", text, re.M) is not None
                      or re.search(rf"^\s*class\s+{re.escape(sym)}\s*[(:]", text, re.M) is not None)
                label = f"{rel}::{sym}"
            if not ok:
                return []
            return [
                f"{lesson_id}: cell NAMES `{label}`, which EXISTS in the tree "
                f"(name match only -- not proof it enforces {lesson_id})"
            ]
        if matcher == "script_flag":
            rel, flag = args[0], args[1]
            p = _safe_repo_path(source_root, rel)
            if p is None or not p.is_file():
                return []
            text = p.read_text(errors="replace")
            # Require a QUOTED flag literal: proof the script REGISTERS the option (argparse),
            # not merely that some comment or docstring mentions it.
            if f'"{flag}"' in text or f"'{flag}'" in text:
                return [
                    f"{lesson_id}: cell NAMES script `{rel}`, which REGISTERS `{flag}` "
                    f"(registration match only -- not proof it enforces {lesson_id})"
                ]
            return []
        if matcher == "agent_charter":
            rel = args[0]
            p = _safe_repo_path(source_root, rel)
            if p is None or not p.is_file():
                return []
            text = p.read_text(errors="replace")
            if re.search(rf"\b{re.escape(lesson_id)}\b", text):
                return [
                    f"{lesson_id}: cell NAMES charter `{rel}`, which CITES {lesson_id} "
                    f"(citation match only -- not proof it enforces {lesson_id})"
                ]
            return []
    except Exception:
        return []
    return []


class StaleUnenforcedRecallReport(NamedTuple):
    """Frozen coverage record for `_stale_unenforced_candidate_issues` (L152 follow-up).

    The point of this record is RECALL, not precision. Before 2026-07-27 the detector
    extracted 0 candidate tokens from all 21 open `**UNENFORCED**` rows and therefore reported
    0 issues -- while an independent audit classified all 21 as already-built stale markers.
    A 0-issue report meant "the extractor saw nothing", not "the queue is clean", and nothing
    in the output distinguished the two. `n_with_extractable_candidate` vs `n_open_unenforced`
    is that distinction, made a number."""
    n_rows: int
    n_unenforced: int
    n_disposed: int
    n_open_unenforced: int
    n_with_extractable_candidate: int
    n_flagged: int
    by_matcher: Tuple[Tuple[str, int], ...]     # (matcher, number of ROWS flagged by it)
    flagged_ids: Tuple[str, ...]
    open_unenforced_ids: Tuple[str, ...]
    # L268 (2026-08-02): a SECOND, separately-labelled count -- rows whose enforcement cell
    # bolds UNENFORCED mid-cell rather than as the leading marker (`_mixed_tier_unenforced_ids`).
    # Reported ALONGSIDE the fields above, never merged into them: the leading-marker regex's
    # precision is load-bearing for the L152 advisory and must not be loosened. Defaulted so
    # every existing direct construction of this NamedTuple (tests, `_EMPTY_STALE_RECALL`)
    # stays valid unchanged.
    n_mixed_tier_unenforced: int = 0
    mixed_tier_unenforced_ids: Tuple[str, ...] = ()


_EMPTY_STALE_RECALL = StaleUnenforcedRecallReport(
    n_rows=0, n_unenforced=0, n_disposed=0, n_open_unenforced=0,
    n_with_extractable_candidate=0, n_flagged=0,
    by_matcher=tuple((m, 0) for m in STALE_MATCHERS), flagged_ids=(), open_unenforced_ids=(),
)


def _stale_unenforced_scan(
    lessons_path: Path = ROOT / "kb" / "lessons" / "00-lessons.md",
    source_root: Path = ROOT,
) -> Tuple[List[str], StaleUnenforcedRecallReport]:
    """(issues, recall report) in one pass. Best-effort/offline: any failure returns
    ([], empty report) and can never poison the gate."""
    try:
        rows = _parse_lesson_rows(lessons_path)
        if not rows:
            return [], _EMPTY_STALE_RECALL
        disposed = _lesson_disposed_ids(rows)
        unenforced = [
            (lid, enf) for lid, _lt, enf in rows if _UNENFORCED_MARKER_RE.match(enf)
        ]
        open_rows = [(lid, enf) for lid, enf in unenforced if lid not in disposed]

        per_row: List[Tuple[str, List[Tuple[str, Tuple[str, ...]]]]] = [
            (lid, _extract_stale_candidates(enf)) for lid, enf in open_rows
        ]
        # One tree scan for every `func` candidate (the original M0 matcher).
        func_names = sorted({args[0] for _lid, cands in per_row for m, args in cands if m == "func"})
        func_defs: Dict[str, List[str]] = {}
        if func_names:
            def_res = {fn: re.compile(rf"^\s*def\s+{re.escape(fn)}\s*\(") for fn in func_names}
            for path in _iter_source_files(source_root):
                try:
                    text = path.read_text(errors="replace")
                except Exception:
                    continue
                lines = text.splitlines()
                for fn, pat in def_res.items():
                    if fn in func_defs:
                        continue
                    if any(pat.match(ln) for ln in lines):
                        func_defs.setdefault(fn, []).append(_rel(path))

        issues: List[str] = []
        flagged_ids: List[str] = []
        matcher_rows: Dict[str, Set[str]] = {m: set() for m in STALE_MATCHERS}
        n_extractable = 0
        for lesson_id, cands in per_row:
            if cands:
                n_extractable += 1
            row_hit = False
            for matcher, args in cands:
                ev = _resolve_stale_candidate(lesson_id, matcher, args, source_root, func_defs)
                if ev:
                    matcher_rows.setdefault(matcher, set()).add(lesson_id)
                    row_hit = True
                    issues.extend(ev)
            if row_hit:
                flagged_ids.append(lesson_id)

        mixed_tier_ids = _mixed_tier_unenforced_ids(rows, disposed)

        report = StaleUnenforcedRecallReport(
            n_rows=len(rows),
            n_unenforced=len(unenforced),
            n_disposed=len(unenforced) - len(open_rows),
            n_open_unenforced=len(open_rows),
            n_with_extractable_candidate=n_extractable,
            n_flagged=len(flagged_ids),
            by_matcher=tuple((m, len(matcher_rows.get(m, set()))) for m in STALE_MATCHERS),
            flagged_ids=tuple(flagged_ids),
            open_unenforced_ids=tuple(lid for lid, _enf in open_rows),
            n_mixed_tier_unenforced=len(mixed_tier_ids),
            mixed_tier_unenforced_ids=mixed_tier_ids,
        )
        return issues, report
    except Exception:
        return [], _EMPTY_STALE_RECALL


def _stale_unenforced_candidate_issues(
    lessons_path: Path = ROOT / "kb" / "lessons" / "00-lessons.md",
    source_root: Path = ROOT,
) -> List[str]:
    """L152's proposed follow-up: a WEAKER but assertable proxy for a stale `UNENFORCED`
    marker in kb/lessons/00-lessons.md -- a row whose enforcement was actually built by a
    later run but whose status was never flipped (the L74/L109/L123 incident).

    Scope, deliberately narrow: only rows whose ENFORCEMENT column OPENS with a bold span whose
    first word is `UNENFORCED` (the ledger's own definition of its standing work queue,
    00-lessons.md line 9) are candidates -- BOTH the `**UNENFORCED**  ...` and the
    `**UNENFORCED  ...**` shapes, see `_UNENFORCED_MARKER_RE` -- minus any ID formally disposed
    of by a `DISPOSES:` marker (grammar in `_lesson_disposed_ids`). The enforcement column is
    taken from `_parse_lesson_rows`, which splits cells escape- and code-span-aware; a naive
    pipe split mis-aligned 14 rows and hid one genuinely-open row (L145) outright.
    Extraction reads the ENFORCEMENT column ONLY,
    never the lesson-text column -- a row's own narrative often names an EXISTING function as
    background context, not as its candidate; L105 names `_segment_bounds()` from
    `scripts/anomaly_sweep.py` as the reason a proposal dies, and that would be a pure false
    positive if lesson text were in scope. Four matchers, all requiring the artifact to exist:

      M0 `func`          -- a backticked `function_name()` containing an underscore (the
                            codebase's private-helper convention; a generic `run()`/`main()`
                            would false-positive on unrelated same-named functions), matched
                            against a `def <name>(` anywhere in the tracked .py/.sql tree.
      M1 `path_symbol`   -- a backticked `dir/file.py::symbol` (or `::Class.method`); fires
                            only if the file exists AND defines that symbol (`def`/`class`;
                            for a dotted symbol, BOTH the class and the method). Very high
                            precision -- the token is a direct pointer at a committed artifact.
      M2 `script_flag`   -- a backticked repo-relative `*.py` path AND a backticked `--flag`
                            token in the SAME cell; fires only if the file exists AND contains
                            the flag as a QUOTED literal (`"--flag"`), i.e. actually registers
                            the option rather than merely mentioning it in prose.
      M3 `agent_charter` -- a backticked `.claude/agents/*.md` path in the cell AND that
                            charter literally citing this row's OWN id (word-boundary `L<NN>`).
                            Both halves are required; this is the "encode it in the edge-prober
                            house style" enforcement family (L105 etc.).

    A bare script/module PATH on its own (e.g. `scripts/invariants.py`) is still deliberately
    NOT matched -- nearly every candidate names an already-existing file as the site where a
    new check should be ADDED, so path-existence alone would flag almost every open row and
    carry no signal. M2 only escapes that because the flag half is the new capability.

    KNOWN PRECISION HAZARDS, accepted and documented rather than papered over:
      * M2 would false-fire on a cell that names an existing script together with a flag that
        script ALREADY had for unrelated reasons (e.g. `scripts/invariants.py` + `--full`).
        No such row exists on the 2026-07-27 ledger; the advisory is non-gating and says
        "confirm before flipping" for exactly this reason.
      * M1 can fire on a NAME COINCIDENCE. WORKED EXAMPLE, L76 (2026-07-27 verifier): its cell
        backticks `tests/test_probe_ladder_coherence.py::
        test_runs_single_deep_snapshot_fails_duration_gate`, which really does exist -- but
        that test asserts on snapshot COUNT (`MIN_SNAPS=2`), the exact mechanism L76's own
        lesson text says is NOT a wall-clock duration gate. The test's NAME says "duration
        gate"; its body does not implement one. L76 is in fact stale, but for an unrelated
        reason (L93 later built `core.bootstrap.collapse_duration_gated_runs`, the helper the
        cell actually asked for) -- so a hit is a pointer to READ the artifact, never evidence
        that the candidate is built. The emitted strings say exactly that and no more
        (`_resolve_stale_candidate`'s wording contract); over-claiming here would be the L165
        failure class reappearing inside the L152 fix.
      * M3 MISSES a charter that encodes a row's rule without naming its ID: requiring the
        `L<NN>` citation is what makes it precise, and it is a real recall cost (measured
        2026-07-27: of the 164 non-UNENFORCED rows, 22 name a charter that does not cite their
        own ID -- the rule is in the house style, the number is not).

    A hit means the row's own named enforcement already exists somewhere in the tree -- a
    HIGH-PRECISION candidate for stale, though never proof (a same-named artifact could
    coincidentally exist; a human/kb-distiller pass still confirms before flipping the row,
    same as the L74/L109/L123 corrections). Recall is PARTIAL and always will be: a row whose
    enforcement is prose-only ("a per-probe methodology gate", "encoded in probe precedents")
    names no machine-checkable artifact at all. `stale_unenforced_recall_report` reports how
    far extraction reached so a 0-issue result can never again be misread as a clean queue.
    Best-effort/offline: any failure returns [] and can never poison the gate."""
    return _stale_unenforced_scan(lessons_path, source_root)[0]


def stale_unenforced_recall_report(
    lessons_path: Path = ROOT / "kb" / "lessons" / "00-lessons.md",
    source_root: Path = ROOT,
) -> StaleUnenforcedRecallReport:
    """Coverage record for the stale-UNENFORCED detector: how many rows it parsed, how many
    are `**UNENFORCED**`, how many of those are formally disposed, how many of the REMAINING
    open rows yielded any extractable candidate at all, and how many were flagged (with a
    per-matcher row count). Best-effort/offline: any failure returns the empty report."""
    return _stale_unenforced_scan(lessons_path, source_root)[1]


def _stale_recall_sentence(recall: StaleUnenforcedRecallReport) -> str:
    """One-line honest coverage statement for the advisory text. Pure."""
    by = ", ".join(f"{m}={n}" for m, n in recall.by_matcher)
    mixed_ids = ", ".join(recall.mixed_tier_unenforced_ids) if recall.mixed_tier_unenforced_ids else "none"
    return (
        f"Extraction reached {recall.n_with_extractable_candidate} of "
        f"{recall.n_open_unenforced} open UNENFORCED row(s) "
        f"({recall.n_disposed} formally disposed via `DISPOSES:`); flagged "
        f"{recall.n_flagged} row(s) [{by}]. The rest name no machine-checkable artifact, so a "
        f"0-issue report is a COVERAGE limit of this detector, NOT evidence of a clean queue. "
        f"Separately (L268, not merged into the counts above): {recall.n_mixed_tier_unenforced} "
        f"row(s) bold UNENFORCED mid-cell rather than as the leading marker [{mixed_ids}]."
    )


def stale_unenforced_candidate_warning(
    issues: List[str],
    recall: Optional[StaleUnenforcedRecallReport] = None,
) -> Optional[str]:
    """Non-gating advisory when an UNENFORCED lesson row's own named candidate already exists
    in the tree -- a likely-stale marker per L152. Pure.

    When `recall` is supplied the message always carries the one-line coverage statement, and
    a zero-issue scan that did NOT reach every open row still emits a coverage-only advisory:
    the 2026-07-27 defect was precisely a silent 0-issue report over a queue that was 100%
    stale. With `recall=None` (legacy call shape) an empty `issues` stays silent."""
    if not issues:
        if recall is None or recall.n_open_unenforced == 0:
            return None
        if recall.n_with_extractable_candidate >= recall.n_open_unenforced:
            return None
        return (
            f"note (non-gating): 0 UNENFORCED lesson row(s) in kb/lessons/00-lessons.md were "
            f"flagged as stale, but this is NOT a clean-queue signal. "
            f"{_stale_recall_sentence(recall)} Advisory only -- does NOT affect the exit code. "
            f"See kb/lessons/00-lessons.md L152."
        )
    n = len(issues)
    n_rows = recall.n_flagged if recall is not None else len({i.split(":", 1)[0] for i in issues})
    examples = "; ".join(issues[:5]) + (", ..." if n > 5 else "")
    tail = f" {_stale_recall_sentence(recall)}" if recall is not None else ""
    return (
        f"warning (non-gating): {n} stale-candidate hit(s) across {n_rows} UNENFORCED lesson "
        f"row(s) in kb/lessons/00-lessons.md NAME an artifact that EXISTS in the tree "
        f"(e.g. {examples}) -- "
        f"a candidate for a stale marker (L74/L109/L123 precedent: the enforcement was built by "
        f"a later run but the row's status was never flipped). A hit is a NAME match, never "
        f"proof the enforcement is built: READ the named artifact before flipping (L76's cell "
        f"names a test that exists but pins snapshot COUNT, not the wall-clock duration gate "
        f"the row asks for -- a name coincidence).{tail} Advisory only -- does NOT "
        f"affect the exit code. See kb/lessons/00-lessons.md L152."
    )


# ─── Dangling test-citation advisory (L205: non-gating, offline-safe) ───────
#
# L205: ledger rows cite tests by pytest node id (`tests/f.py::test_name`) as their ENFORCEMENT
# EVIDENCE, and the lane that owns test files may not edit `kb/`. A rename made in the test lane
# therefore leaves a dangling citation that the renaming agent cannot repair and the kb lane
# cannot see — silently downgrading a `test`-tier row to an unverifiable prose claim, which is
# the exact failure this ledger exists to prevent.
#
# The check: every `::test_...` token cited by `kb/`, `findings/` and `LOOP-QUEUE.md` must
# resolve to a `def <name>(` under `tests/`. NON-GATING on purpose, for two independent reasons:
# (1) it is a LEXICAL proxy over prose (per L155 its constructed-negative corpus in
# `tests/test_invariants.py` is its only coverage claim), and (2) repairing a hit means editing
# `kb/`, which the code lane may not do — a gate the on-call lane cannot clear would halt the
# loop. Two real dangling citations exist on the 2026-07-28 tree; both are honest test renames
# (`test_acceptance_8_l127_hyperliquid_funding_join_stale` and
# `test_acceptance_exactly_one_real_finding_is_recovery_class`), i.e. the advisory fires on the
# defect it was written for, not on noise.

# Docs whose `::test_` tokens are treated as citations (relative to ROOT).
TEST_CITATION_DOC_GLOBS = ("kb/**/*.md", "findings/**/*.md", "LOOP-QUEUE.md")

# `tests/f.py::test_x`, `f.py::test_x`, or a bare continuation `::test_x` (the ledger's own
# house style for a second node id in the same cell). A trailing `...`/`*` marks an ELIDED
# citation — the ledger routinely writes `::test_parse_iso_utc_*` for a family of tests.
_TEST_CITATION_RE = re.compile(
    r"(?:(?P<path>[A-Za-z0-9_][A-Za-z0-9_./-]*\.py))?"
    r"::(?P<name>test_[A-Za-z0-9_]*)(?P<tail>\.\.\.|\*)?"
)
_TEST_DEF_RE = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+(test_[A-Za-z0-9_]*)[ \t]*\(", re.M)

# Metasyntactic tokens: prose ABOUT the citation grammar, not citations of a real test. Kept as
# an explicit, short, documented list rather than a heuristic — a heuristic here would quietly
# suppress real node ids (L197: a matcher must never over-claim what it suppresses).
CITATION_PLACEHOLDER_NAMES = frozenset({"test_", "test_name", "test_foo", "test_x"})
# An elided citation must carry at least this many characters of prefix to be RESOLVABLE by
# prefix match; a shorter one (`::test_*`) matches nearly every test and would be a vacuous
# pass, so it is SKIPPED (reported as a coverage limit) rather than silently accepted.
CITATION_MIN_PREFIX_LEN = 10


def _test_def_index(tests_dir: Path) -> Tuple[Dict[str, Set[str]], Set[str]]:
    """(per-file test-def names keyed by BASENAME, union of all names) for `tests/`.
    Keyed by basename so `test_invariants.py::x` and `tests/test_invariants.py::x` resolve
    identically — both shapes appear in the ledger. Best-effort: unreadable files are skipped."""
    per_file: Dict[str, Set[str]] = {}
    every: Set[str] = set()
    try:
        files = sorted(tests_dir.rglob("*.py"))
    except Exception:
        return {}, set()
    for path in files:
        try:
            names = {m.group(1) for m in _TEST_DEF_RE.finditer(path.read_text())}
        except Exception:
            continue
        per_file.setdefault(path.name, set()).update(names)
        every |= names
    return per_file, every


def _cited_test_node_issues(
    root: Path = ROOT,
    tests_dir: Optional[Path] = None,
) -> List[str]:
    """Pytest node-id citations in `kb/`, `findings/` and `LOOP-QUEUE.md` that no longer resolve
    to a test definition under `tests/` — L205's dangling-citation failure mode.

    Resolution rules, deliberately conservative (a false positive here sends a human to re-read
    a document for nothing, and worse, trains the reader to ignore the advisory):
      * PATH-QUALIFIED (`tests/f.py::test_x`) — the cited FILE must exist under `tests/` (matched
        by basename, see `_test_def_index`) and must define that test. A path naming a file with
        no test defs at all is reported as an unresolved FILE, not as a missing test.
      * BARE (`::test_x`) — the ledger's continuation shape for a second node id in one cell;
        resolves against the union of every test name in the tree. Weaker (it cannot detect a
        test MOVED between files) but that is the strongest honest reading of the token.
      * ELIDED (`::test_parse_iso_utc_*`, `::test_acceptance_6_...`, or a name ending in `_`) —
        resolved by PREFIX match, since the citation deliberately names a family. A prefix
        shorter than `CITATION_MIN_PREFIX_LEN` is skipped entirely (vacuous).
      * `CITATION_PLACEHOLDER_NAMES` are skipped: prose about the citation grammar itself.

    COVERAGE, stated honestly: a hit is a NAME resolution only. This can never verify that the
    resolved test still asserts what the citing row CLAIMS it asserts (L165: no static scanner
    can check a citation's accuracy, only its resolvability) — a test can be gutted in place and
    keep its name. Best-effort/offline: any failure returns [] and can never poison the gate.
    Returns sorted `doc:line: <token> -- <reason>` strings, deduplicated."""
    try:
        tdir = tests_dir if tests_dir is not None else root / "tests"
        per_file, every = _test_def_index(tdir)
        docs: List[Path] = []
        for pattern in TEST_CITATION_DOC_GLOBS:
            docs.extend(p for p in root.glob(pattern) if p.is_file())
        issues: Set[str] = set()
        for doc in sorted(set(docs)):
            try:
                lines = doc.read_text().splitlines()
            except Exception:
                continue
            rel = doc.relative_to(root).as_posix() if doc.is_absolute() else doc.as_posix()
            for lineno, line in enumerate(lines, 1):
                for m in _TEST_CITATION_RE.finditer(line):
                    name = m.group("name")
                    if name in CITATION_PLACEHOLDER_NAMES:
                        continue
                    elided = bool(m.group("tail")) or name.endswith("_")
                    if elided and len(name) < CITATION_MIN_PREFIX_LEN:
                        continue
                    cited_path = m.group("path")
                    if cited_path is not None:
                        base = cited_path.rsplit("/", 1)[-1]
                        pool = per_file.get(base)
                        if pool is None:
                            issues.add(
                                f"{rel}:{lineno}: `{m.group(0)}` -- no such test file under "
                                f"{tdir.name}/"
                            )
                            continue
                    else:
                        pool = every
                    ok = (
                        any(n.startswith(name) for n in pool) if elided else name in pool
                    )
                    if not ok:
                        where = cited_path if cited_path is not None else f"{tdir.name}/"
                        issues.add(
                            f"{rel}:{lineno}: `{m.group(0)}` -- no `def {name}(` in {where}"
                        )
        return sorted(issues)
    except Exception:
        return []


def dangling_test_citation_warning(issues: List[str]) -> Optional[str]:
    """Non-gating advisory when a `kb/`/`findings/`/`LOOP-QUEUE.md` pytest node-id citation no
    longer resolves to a test under `tests/` (L205), else None. Pure."""
    if not issues:
        return None
    n = len(issues)
    examples = "; ".join(issues[:5]) + (", ..." if n > 5 else "")
    return (
        f"warning (non-gating): {n} pytest node-id citation(s) in kb/ / findings/ / "
        f"LOOP-QUEUE.md do not resolve to a test under tests/ (e.g. {examples}). A ledger row "
        f"cites a test as its ENFORCEMENT EVIDENCE, so a dangling citation silently downgrades "
        f"a `test`-tier row to an unverifiable prose claim — grep the citation before renaming "
        f"or deleting a test, and repair the citing document in the same pass. Resolution is by "
        f"NAME only: it cannot check the test still asserts what the row claims (L165). "
        f"Advisory only -- does NOT affect the exit code. See kb/lessons/00-lessons.md L205."
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
        # L221 advisory: a single-hour leg's hour-equality gate admitted repeat passes on the
        # same UTC day (rate gate, not idempotence gate) and the extra passes are byte-redundant
        # re-capture. Non-gating; BaseException-wrapped for the same reason as the stanzas below
        # (it dynamically exec's tape_gap_monitor.py, and a formatter raise must not become a gate).
        try:
            idem_warning = single_hour_leg_idempotence_warning(
                _single_hour_leg_idempotence_issues())
            if idem_warning:
                sys.stderr.write(idem_warning + "\n")
        except BaseException:
            sys.stderr.write("note: single-hour-gate idempotence advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
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
        # L168/L169 advisory: tape/orderbook_depth/ crypto records that are present,
        # well-formed, and HOLLOW (empty book) because the fetch landed after the ticker's
        # own close — invisible to completeness_ok. Non-gating, same BaseException-wrapped
        # posture as the collector-health advisory above.
        try:
            hollow_warning = hollow_crypto_ladder_warning(_hollow_crypto_ladder_issues())
            if hollow_warning:
                sys.stderr.write(hollow_warning + "\n")
        except BaseException:
            sys.stderr.write("note: hollow crypto-ladder advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
        # L185 advisory: a capped, newest-first-paginated collector whose per-pass captured
        # event-time window is far narrower than its own firing interval (settlement_ledger:
        # 5000 rows, no min/max_close_ts, ~1.3-3.8h reached per 24h fire). Non-gating — the
        # mismatch is a collector DESIGN property no cloud run can repair mid-loop, so gating
        # would halt the loop indefinitely. Wrapped in `except BaseException` for the same
        # reason as the collector-health stanza above: the detector self-guards, but a raise in
        # the FORMATTER or a non-str return (making `+ "\n"` a TypeError) would otherwise reach
        # the exit code and turn a non-gating advisory into a gate (the L156 DEFECT-1 lesson).
        try:
            capped_span_warning = capped_pagination_span_warning(_capped_pagination_span_issues())
            if capped_span_warning:
                sys.stderr.write(capped_span_warning + "\n")
        except BaseException:
            sys.stderr.write("note: capped-pagination span advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
        # L270 advisory: a bounded-collector family (universe_sweep/settlement_ledger) whose
        # committed captures sit AT the collector's own page cap on (nearly) every pass, so
        # its own completeness_ok is structurally False and hourly_pass's AND fires the VPS
        # pager on a permanent, already-known fact rather than a new failure. Non-gating --
        # raising a cap or re-scoping hourly_pass's AND is a design call for Ryan, not
        # something a cloud run can repair mid-loop. Wrapped in `except BaseException` for
        # the same reason as the stanza above: a raise in the FORMATTER or a non-str return
        # must not turn a non-gating advisory into a gate (the L156 DEFECT-1 lesson).
        try:
            cap_saturation_warning = completeness_cap_saturation_warning(
                _completeness_cap_saturation_issues())
            if cap_saturation_warning:
                sys.stderr.write(cap_saturation_warning + "\n")
        except BaseException:
            sys.stderr.write("note: completeness-cap saturation advisory could not be "
                             "computed (non-gating; exit code unaffected)\n")
        # L210 advisory: a `capture_id` shared by two DISTINCT collector invocations (a
        # one-shot backfill landing in the same wall-clock second as a scheduled pass), so
        # the same logical item appears twice under one id and any consumer grouping by that
        # key merges two payloads. Non-gating — a historical property of committed
        # append-only tape that no run can retroactively repair. Wrapped in
        # `except BaseException` for the same reason as the stanza above: a raise in the
        # FORMATTER must not turn a non-gating advisory into a gate (L156 DEFECT-1).
        # L208 advisory: a window-bucketed family whose EXPECTED window grid contains windows
        # with zero capture passes — invisible to any density statistic built from observed
        # windows only. Non-gating: a missed funding/settlement window is permanently
        # unrecoverable (no re-fetch), so gating would halt the loop over an unfixable past.
        # Wrapped in `except BaseException` for the L156 DEFECT-1 reason: a raise in the
        # FORMATTER must not turn a non-gating advisory into a gate.
        try:
            window_grid_warning = window_grid_coverage_warning(_window_grid_coverage_issues())
            if window_grid_warning:
                sys.stderr.write(window_grid_warning + "\n")
        except BaseException:
            sys.stderr.write("note: expected-window-grid advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
        try:
            dup_capture_warning = duplicate_capture_id_warning(_duplicate_capture_id_issues())
            if dup_capture_warning:
                sys.stderr.write(dup_capture_warning + "\n")
        except BaseException:
            sys.stderr.write("note: colliding-capture_id advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
        # L223 advisory: a tape/econ_prints/ series_key that regressed from a real `settled`
        # status back to `no_settled_events` for 3+ consecutive passes (the gdp leg: one real
        # settlement, then 340+ silent no_settled_events passes). Non-gating — the fix is a
        # collector/upstream-API change no cloud run can make mid-loop. Wrapped in
        # `except BaseException` for the same reason as the stanzas above: a raise in the
        # FORMATTER must not turn a non-gating advisory into a gate (L156 DEFECT-1).
        try:
            econ_regression_warning = econ_prints_settlement_regression_warning(
                _econ_prints_settlement_regression_issues())
            if econ_regression_warning:
                sys.stderr.write(econ_regression_warning + "\n")
        except BaseException:
            sys.stderr.write("note: econ-prints settlement-regression advisory could not be "
                             "computed (non-gating; exit code unaffected)\n")
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
        # L232 advisory: a file under scripts/ importing the `scripts.` package with no
        # repo-root sys.path bootstrap ahead of it — breaks `python3 scripts/foo.py` (the form
        # kb/ and findings/ cite) while every in-process import test stays green. Non-gating —
        # stderr only, never flips the exit code.
        cross_import_warning = scripts_cross_import_bootstrap_warning(
            _scripts_cross_import_bootstrap_issues())
        if cross_import_warning:
            sys.stderr.write(cross_import_warning + "\n")
        # L147 advisory: kb/lessons/00-lessons.md assigning the same lesson ID to more than
        # one row (2026-07-24 incident: L130/L131 each collided). Non-gating — stderr only.
        dup_lesson_warning = duplicate_lesson_id_warning(_duplicate_lesson_id_issues())
        if dup_lesson_warning:
            sys.stderr.write(dup_lesson_warning + "\n")
        # L152 advisory: an UNENFORCED lesson row whose own named candidate (function,
        # path::symbol, script+CLI flag, or agent-charter house-style bullet) already exists in
        # the tree — a high-precision proxy for a stale marker (the L74/L109/L123 incident).
        # Carries its own RECALL statement: the 2026-07-27 defect was a silent 0-issue report
        # over a queue that was 100% stale, because the extractor reached none of it. Non-gating
        # — stderr only, and wrapped like the collector-health/dwell stanzas so neither the
        # detector, the formatter raising, nor a non-str return can reach the exit code (the
        # L156 DEFECT-1 lesson).
        try:
            stale_issues, stale_recall = _stale_unenforced_scan()
            stale_warning = stale_unenforced_candidate_warning(stale_issues, stale_recall)
            if stale_warning:
                sys.stderr.write(stale_warning + "\n")
        except BaseException:
            sys.stderr.write("note: stale-UNENFORCED-candidate advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
        # L205 advisory: a pytest node-id citation in kb/ / findings/ / LOOP-QUEUE.md that no
        # longer resolves to a test under tests/ (a rename in the test lane the kb lane cannot
        # see). Non-gating: repairing a hit means editing kb/, which the code lane may not do,
        # so a gate here would be one the on-call lane cannot clear. Wrapped in
        # `except BaseException` like the stanzas above so neither the detector, the formatter
        # raising, nor a non-str return can reach the exit code (the L156 DEFECT-1 lesson).
        try:
            citation_warning = dangling_test_citation_warning(_cited_test_node_issues())
            if citation_warning:
                sys.stderr.write(citation_warning + "\n")
        except BaseException:
            sys.stderr.write("note: dangling-test-citation advisory could not be computed "
                             "(non-gating; exit code unaffected)\n")
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
