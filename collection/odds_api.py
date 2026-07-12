"""The-Odds-API leg of the sports paired-odds collector (READ-ONLY) — Q1's second half.

LOOP-QUEUE.md Q1: when `ODDS_API_KEY` is present, each Kalshi moneyline game captured by
`collection/sports_pairs.py` is paired with a sharp sportsbook's h2h line (Pinnacle
preferred), de-vigged to a fair probability per outcome. A de-vig is a model, not a fill —
every number this module produces is tagged `synthetic` (CLAUDE.md trust defaults); the
only fillable prices on the tape line remain the Kalshi `real_ask` legs.

Self-activating: `sports_pairs.run()` calls `enrich_records()` only when a key exists in
the environment, so the moment `ODDS_API_KEY` appears (cloud env var on the kalshi-loops
environment, or a local export) the hourly pass starts pairing without a code change. No
key -> the Kalshi leg is untouched and every game stays `{"status": "blocked_key"}`.

Matching is grounded in fields Kalshi actually serves (probed live 2026-07-03):
`occurrence_datetime` is the game start (matches the-odds-api `commence_time`, the primary
key) and `yes_sub_title` is "Reg Time: <team name or Tie>" (the per-outcome team name — no
abbreviation guessing from outcome codes). Both are persisted on the v2 tape record even
when no key is present, so the match is replayable offline later.

Honest statuses per game (never a silent drop): `matched` / `blocked_key` /
`unmapped_series` / `not_selected` / `sport_not_active` / `fetch_error` / `quota_floor` /
`no_match` / `ambiguous` / `no_bookmaker`.

Quota discipline (free tier = 500 credits/month; one h2h call with one region costs 1):
- `/v4/sports` is quota-free and fetched once per pass to runtime-verify the static
  series->sport map (a wrong or out-of-season key becomes `sport_not_active`, not a guess).
- Default sport selection = S7's targets only (`DEFAULT_SPORTS`); widen with
  `ODDS_API_SPORTS=all` or a comma list of sport keys / Kalshi series tickers.
- `ODDS_API_QUOTA_FLOOR` (default 50): once `x-requests-remaining` drops below it, the
  remaining sports this pass are marked `quota_floor` instead of fetched — a free key
  degrades loudly, it is never silently burned to zero.
- `ODDS_API_REGIONS` (default `eu` — the region that carries Pinnacle) sets per-call cost:
  cost = number of regions.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import requests

from core.canonical import canonical_json, sha256_hex

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Kalshi series ticker -> the-odds-api sport_key. Best-effort from the-odds-api's published
# catalogue; every entry is runtime-verified against the live quota-free /v4/sports list
# each pass, so a stale/wrong key surfaces as `sport_not_active`, never a bad fetch loop.
SPORT_KEY_BY_SERIES = {
    "KXWCGAME": "soccer_fifa_world_cup",
    "KXNFLGAME": "americanfootball_nfl",
    "KXNBAGAME": "basketball_nba",
    "KXMLBGAME": "baseball_mlb",
    "KXWNBAGAME": "basketball_wnba",
    "KXNHLGAME": "icehockey_nhl",
    "KXAFLGAME": "aussierules_afl",
    "KXKBOGAME": "baseball_kbo",
    "KXNPBGAME": "baseball_npb",
    "KXALLSVENSKANGAME": "soccer_sweden_allsvenskan",
    "KXCHNSLGAME": "soccer_china_superleague",
    "KXBRASILEIROBGAME": "soccer_brazil_serie_b",
    "KXEPLGAME": "soccer_epl",
    "KXLALIGAGAME": "soccer_spain_la_liga",
    "KXUCLGAME": "soccer_uefa_champs_league",
    "KXNCAAFGAME": "americanfootball_ncaaf",
}

# S7's named targets (NFL/NBA) + the time-sensitive World Cup (Q1 deadline Jul 19).
# 24 hourly passes/day x 1 credit (regions=eu) x 1 in-season sport fits a 500/month key.
DEFAULT_SPORTS = ("soccer_fifa_world_cup", "americanfootball_nfl", "basketball_nba")

# Sharp-first bookmaker order (S7 anchors on Pinnacle). If none of these carries h2h for
# an event, the first available bookmaker is used and recorded — the analysis side filters
# on `bookmaker`, the tape never throws data away.
PREFERRED_BOOKMAKERS = ("pinnacle", "betonlineag", "lowvig", "betfair_ex_eu", "marathonbet")

DEFAULT_QUOTA_FLOOR = 50
COMMENCE_WINDOW = timedelta(hours=3)

# Acceptance bars for a game<->event match (pinned by tests): both teams must show some
# signal, the pair must be strong overall, and the winner must clear the runner-up.
MIN_SIDE_SCORE = 0.3
MIN_TOTAL_SCORE = 1.2
MIN_MARGIN = 0.25

_SUBTITLE_PREFIX_RE = re.compile(r"^[^:]{0,40}:\s*")
_TITLE_RE = re.compile(r"^(?P<a>.+?)\s+vs\.?\s+(?P<b>.+?)\s*:?\s*winner\??\s*$", re.I)
_DRAW_NAMES = {"draw", "tie"}

# Club-suffix noise dropped before token comparison; never dropped if it would empty the
# name (AIK, IF Elfsborg's "IF" is noise, the club "IF" alone would not be).
_STOP_TOKENS = {"fc", "cf", "sc", "afc", "cd", "ac", "fk", "bk", "if", "club", "de",
                "do", "da", "the"}


# --------------------------------------------------------------------------- #
# de-vig (Q1: SYNTHETIC, never a fill)
# --------------------------------------------------------------------------- #
def devig_multiplicative(decimal_odds: List[float]) -> List[float]:
    """Proportional de-vig: 1/odds implied probabilities, normalized to sum to 1.0.

    The output is `synthetic` (CLAUDE.md: "a de-vig is a model, not a fill") — it estimates
    the sharp book's fair probability net of vig, it is never itself a tradeable price.
    """
    if not decimal_odds or any(o <= 1.0 for o in decimal_odds):
        raise ValueError(f"decimal odds must each be > 1.0, got {decimal_odds!r}")
    implied = [1.0 / o for o in decimal_odds]
    total = sum(implied)
    return [x / total for x in implied]


# --------------------------------------------------------------------------- #
# name normalization + team matching
# --------------------------------------------------------------------------- #
def normalize_team(name: str) -> List[str]:
    """Accent-fold, lowercase, strip punctuation, drop club-suffix noise tokens (unless
    that would empty the name). Returns the token list."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [t for t in s.split() if t]
    kept = [t for t in toks if t not in _STOP_TOKENS]
    return kept or toks


def _initials_match(abbrev: str, tokens: Sequence[str]) -> bool:
    """True if `abbrev` equals the joined initials of any consecutive run of `tokens`
    ('ws' matches ['white','sox']; 'la' matches ['los','angeles', ...])."""
    n = len(abbrev)
    for i in range(len(tokens) - n + 1):
        if "".join(t[0] for t in tokens[i:i + n]) == abbrev:
            return True
    return False


def team_match_score(a_name: str, b_name: str) -> float:
    """Similarity in [0,1] between two team names across the two venues' conventions.
    Exact=1.0; token-set containment=0.85; else token overlap with abbreviation credit
    (short tokens matching initials-runs or token prefixes), capped at 0.8."""
    a, b = normalize_team(a_name), normalize_team(b_name)
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    if sa == sb:
        return 1.0
    if sa <= sb or sb <= sa:
        return 0.85
    matched = len(sa & sb)
    for t in sa - sb:
        if len(t) <= 4 and (_initials_match(t, b) or any(tok.startswith(t) for tok in sb)):
            matched += 1
    for t in sb - sa:
        if len(t) <= 4 and (_initials_match(t, a) or any(tok.startswith(t) for tok in sa)):
            matched += 1
    return min(0.8, 0.8 * matched / min(len(sa), len(sb)))


def parse_game_title(title: str) -> Optional[Tuple[str, str]]:
    """'Portugal vs Croatia Winner?' -> ('Portugal', 'Croatia'); None if not that grammar."""
    m = _TITLE_RE.match((title or "").strip())
    if not m:
        return None
    return m["a"].strip(), m["b"].strip()


def parse_outcome_name(yes_sub_title: Optional[str]) -> Optional[str]:
    """\"Reg Time: Portugal\" -> \"Portugal\"; plain subtitles pass through; None stays None."""
    if not yes_sub_title:
        return None
    return _SUBTITLE_PREFIX_RE.sub("", yes_sub_title.strip()).strip() or None


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# game <-> odds-api event matching
# --------------------------------------------------------------------------- #
def _time_ok(record: Dict[str, Any], event: Dict[str, Any]) -> bool:
    """Primary key: |game_start - commence_time| <= COMMENCE_WINDOW when both are known;
    fall back to commence date within +/-1 day of the ticker's game_date."""
    game_start = _parse_iso(record.get("game_start"))
    commence = _parse_iso(event.get("commence_time"))
    if commence is None:
        return False
    if game_start is not None:
        return abs(game_start - commence) <= COMMENCE_WINDOW
    game_date = record.get("game_date")
    if not game_date:
        return False
    try:
        gd = datetime.strptime(game_date, "%Y-%m-%d").date()
    except ValueError:
        return False
    return abs((commence.date() - gd).days) <= 1


def _pair_score(record: Dict[str, Any], event: Dict[str, Any]) -> float:
    """Best-orientation sum of the two per-team scores; 0 unless both sides clear
    MIN_SIDE_SCORE (a one-team coincidence is not a match)."""
    teams = parse_game_title(record.get("game_title", ""))
    if not teams:
        return 0.0
    a, b = teams
    home, away = event.get("home_team", ""), event.get("away_team", "")
    best = 0.0
    for x, y in ((home, away), (away, home)):
        s1, s2 = team_match_score(a, x), team_match_score(b, y)
        if min(s1, s2) >= MIN_SIDE_SCORE:
            best = max(best, s1 + s2)
    return best


def match_event(record: Dict[str, Any], events: List[Dict[str, Any]]
                ) -> Tuple[Optional[Dict[str, Any]], str, float]:
    """Pick the unique odds-api event for one Kalshi game. Returns (event, status, score)
    where status is 'matched' / 'no_match' / 'ambiguous'."""
    scored = [(ev, _pair_score(record, ev)) for ev in events if _time_ok(record, ev)]
    scored = [(ev, s) for ev, s in scored if s >= MIN_TOTAL_SCORE]
    if not scored:
        return None, "no_match", 0.0
    scored.sort(key=lambda p: p[1], reverse=True)
    if len(scored) > 1 and scored[0][1] - scored[1][1] < MIN_MARGIN:
        return None, "ambiguous", scored[0][1]
    return scored[0][0], "matched", scored[0][1]


# --------------------------------------------------------------------------- #
# bookmaker selection + per-outcome fair-prob pairing
# --------------------------------------------------------------------------- #
def _pick_bookmaker(event: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """(bookmaker, its h2h market), sharp-preference order then first-available."""
    books = {bk.get("key"): bk for bk in event.get("bookmakers") or []}
    ordered = [books[k] for k in PREFERRED_BOOKMAKERS if k in books]
    ordered += [bk for k, bk in books.items() if k not in PREFERRED_BOOKMAKERS]
    for bk in ordered:
        for mkt in bk.get("markets") or []:
            if mkt.get("key") == "h2h" and mkt.get("outcomes"):
                return bk, mkt
    return None


def _book_outcome_for(kalshi_name: Optional[str], book_outcomes: List[Dict[str, Any]]
                      ) -> Optional[Dict[str, Any]]:
    """Map one Kalshi outcome name to the book's h2h outcome (Tie <-> Draw special-cased);
    requires a unique best match clearing MIN_SIDE_SCORE."""
    if not kalshi_name:
        return None
    if kalshi_name.strip().lower() in _DRAW_NAMES:
        for o in book_outcomes:
            if (o.get("name") or "").strip().lower() in _DRAW_NAMES:
                return o
        return None
    scored = []
    for o in book_outcomes:
        name = o.get("name") or ""
        if name.strip().lower() in _DRAW_NAMES:
            continue
        scored.append((o, team_match_score(kalshi_name, name)))
    scored = [(o, s) for o, s in scored if s >= MIN_SIDE_SCORE]
    if not scored:
        return None
    scored.sort(key=lambda p: p[1], reverse=True)
    if len(scored) > 1 and scored[0][1] - scored[1][1] < 1e-9:
        return None    # two book outcomes tied for the same Kalshi name -> refuse to guess
    return scored[0][0]


def build_odds_leg(record: Dict[str, Any], event: Dict[str, Any], sport_key: str,
                   match_score: float) -> Dict[str, Any]:
    """The `matched` odds_leg body: raw decimal odds + de-vigged fair prob per Kalshi
    outcome, all `synthetic`. Unmappable outcomes stay explicit nulls (`partial`)."""
    picked = _pick_bookmaker(event)
    if picked is None:
        return {"status": "no_bookmaker", "sport_key": sport_key,
                "odds_event_id": event.get("id")}
    bk, mkt = picked
    book_outcomes = mkt["outcomes"]
    odds = [float(o["price"]) for o in book_outcomes]
    fair_by_name = dict(zip((o.get("name") for o in book_outcomes),
                            devig_multiplicative(odds)))
    paired = []
    n_mapped = 0
    for out in record.get("outcomes", []):
        kalshi_name = out.get("outcome_name") or out.get("outcome_code")
        bo = _book_outcome_for(kalshi_name, book_outcomes)
        if bo is not None:
            n_mapped += 1
        paired.append({
            "kalshi_ticker": out.get("ticker"),
            "kalshi_outcome_name": kalshi_name,
            "book_outcome": bo.get("name") if bo else None,
            "decimal_odds": float(bo["price"]) if bo else None,
            "fair_prob": fair_by_name.get(bo.get("name")) if bo else None,
        })
    full = (n_mapped == len(paired) == len(book_outcomes)) and n_mapped > 0
    return {
        "status": "matched",
        "sport_key": sport_key,
        "odds_event_id": event.get("id"),
        "commence_time": event.get("commence_time"),
        "home_team": event.get("home_team"),
        "away_team": event.get("away_team"),
        "bookmaker": bk.get("key"),
        "bookmaker_preferred": bk.get("key") == PREFERRED_BOOKMAKERS[0],
        "bookmaker_last_update": mkt.get("last_update"),
        "match_score": round(match_score, 4),
        "book_overround": sum(1.0 / o for o in odds) - 1.0,
        "outcomes": paired,
        "outcome_coverage": "full" if full else "partial",
        "price_source_tag": "synthetic",
    }


# --------------------------------------------------------------------------- #
# fetching (injectable for offline tests)
# --------------------------------------------------------------------------- #
def _default_http_get(url: str, params: Dict[str, Any]
                      ) -> Tuple[int, str, Dict[str, str]]:
    r = requests.get(url, params=params, timeout=30)
    return r.status_code, r.text, {k.lower(): v for k, v in r.headers.items()}


def _fetch_json(http_get: Callable, url: str, params: Dict[str, Any]
                ) -> Tuple[Any, str, Dict[str, str]]:
    status, text, headers = http_get(url, params)
    if status != 200:
        raise RuntimeError(f"odds-api HTTP {status} for {url.rsplit('/', 2)[-2:]}")
    import json as _json
    return _json.loads(text), text, {k.lower(): v for k, v in headers.items()}


def _header_int(headers: Dict[str, str], name: str) -> Optional[int]:
    try:
        return int(float(headers.get(name, "")))
    except (TypeError, ValueError):
        return None


def _selected_sports(env: Dict[str, str]) -> Optional[set]:
    """None means 'all mapped sports'; otherwise the selected sport_key set (entries may
    be sport keys or Kalshi series tickers)."""
    raw = (env.get("ODDS_API_SPORTS") or "").strip()
    if raw.lower() == "all":
        return None
    if not raw:
        return set(DEFAULT_SPORTS)
    out = set()
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.add(SPORT_KEY_BY_SERIES.get(tok.upper(), tok.lower()))
    return out


# --------------------------------------------------------------------------- #
# orchestration — enrich one pass's records in place
# --------------------------------------------------------------------------- #
def enrich_records(records: List[Dict[str, Any]], api_key: str,
                   http_get: Optional[Callable] = None,
                   env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Mutates each record's `odds_leg` with an honest status (see module docstring) and
    returns the pass-level odds summary. Any failure degrades that sport's games to an
    error status — the Kalshi leg is never at risk from this function."""
    if env is None:
        import os
        env = dict(os.environ)
    http_get = http_get or _default_http_get
    regions = env.get("ODDS_API_REGIONS", "eu")
    try:
        quota_floor = int(env.get("ODDS_API_QUOTA_FLOOR", str(DEFAULT_QUOTA_FLOOR)))
    except ValueError:
        quota_floor = DEFAULT_QUOTA_FLOOR
    selected = _selected_sports(env)

    by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        sport_key = SPORT_KEY_BY_SERIES.get(rec.get("series", ""))
        if sport_key is None:
            rec["odds_leg"] = {"status": "unmapped_series"}
        elif selected is not None and sport_key not in selected:
            rec["odds_leg"] = {"status": "not_selected", "sport_key": sport_key}
        else:
            by_sport.setdefault(sport_key, []).append(rec)

    quota_remaining: Optional[int] = None
    quota_used: Optional[int] = None
    raw_hashes: List[List[str]] = []
    n_matched = 0

    try:
        catalogue, raw, _ = _fetch_json(http_get, f"{ODDS_API_BASE}/sports",
                                        {"apiKey": api_key})
        active = {s.get("key") for s in catalogue if s.get("active", True)}
        raw_hashes.append(["_sports_catalogue", sha256_hex(raw.encode("utf-8"))])
    except Exception as exc:
        for recs in by_sport.values():
            for rec in recs:
                rec["odds_leg"] = {"status": "fetch_error", "error": f"sports_catalogue: {exc}"}
        return _summary(records, None, None, raw_hashes, 0)

    for sport_key in sorted(by_sport):
        recs = by_sport[sport_key]
        if sport_key not in active:
            for rec in recs:
                rec["odds_leg"] = {"status": "sport_not_active", "sport_key": sport_key}
            continue
        if quota_remaining is not None and quota_remaining < quota_floor:
            for rec in recs:
                rec["odds_leg"] = {"status": "quota_floor", "sport_key": sport_key,
                                   "quota_remaining": quota_remaining}
            continue
        try:
            events, raw, headers = _fetch_json(
                http_get, f"{ODDS_API_BASE}/sports/{sport_key}/odds",
                {"apiKey": api_key, "regions": regions, "markets": "h2h",
                 "oddsFormat": "decimal", "dateFormat": "iso"})
        except Exception as exc:
            for rec in recs:
                rec["odds_leg"] = {"status": "fetch_error", "sport_key": sport_key,
                                   "error": str(exc)}
            continue
        raw_hashes.append([sport_key, sha256_hex(raw.encode("utf-8"))])
        remaining = _header_int(headers, "x-requests-remaining")
        if remaining is not None:
            quota_remaining = remaining
        used = _header_int(headers, "x-requests-used")
        if used is not None:
            quota_used = used
        for rec in recs:
            event, status, score = match_event(rec, events)
            if event is None:
                rec["odds_leg"] = {"status": status, "sport_key": sport_key,
                                   "n_events_seen": len(events)}
            else:
                rec["odds_leg"] = build_odds_leg(rec, event, sport_key, score)
                if rec["odds_leg"]["status"] == "matched":
                    n_matched += 1

    return _summary(records, quota_remaining, quota_used, raw_hashes, n_matched)


def _summary(records: List[Dict[str, Any]], quota_remaining: Optional[int],
             quota_used: Optional[int], raw_hashes: List[List[str]],
             n_matched: int) -> Dict[str, Any]:
    status_counts: Dict[str, int] = {}
    for rec in records:
        st = (rec.get("odds_leg") or {}).get("status", "absent")
        status_counts[st] = status_counts.get(st, 0) + 1
    return {
        "n_matched": n_matched,
        "status_counts": status_counts,
        "quota_remaining": quota_remaining,
        "quota_used": quota_used,
        "raw_sha256": sha256_hex(canonical_json(sorted(raw_hashes))),
    }
