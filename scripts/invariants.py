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
from pathlib import Path
from typing import Callable, List, Optional, Tuple

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


STATIC_INVARIANTS: List[Tuple[str, Callable[[Path, str], Optional[str]]]] = [
    ("no_gefs", inv_no_gefs),
    ("no_bare_pstdev", inv_no_bare_pstdev),
    ("no_pstdev_import", inv_no_pstdev_import),
    ("no_yes_ask_arithmetic", inv_no_yes_ask_arithmetic),
    ("no_static_rho_point_four", inv_no_static_rho_point_four),
    ("no_handrolled_fee_rate", inv_no_handrolled_fee_rate),
    ("no_http_server", inv_no_http_server),
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

    if failures:
        sys.stderr.write(f"invariants: {len(failures)} violation(s)\n")
        for f in failures:
            sys.stderr.write(f + "\n")
        return 2
    sys.stdout.write("invariants: all green\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
