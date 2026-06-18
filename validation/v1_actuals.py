"""V1 — Actuals validator (settlement truth).

For each curated city over the sample window, reconcile three INDEPENDENT pipelines:
  CLI   — NWS Climatological Report high/low via IEM (the settlement truth)
  METAR — IEM daily summary max/min derived from ASOS observations
  GHCN  — NCEI GHCN-Daily TMAX/TMIN (independent QC'd daily)

A city-day is `clean` only when CLI is present and agrees with >=1 independent
source within tolerance for BOTH max and min. Disagreement >= 2 degF, impossible
values, or a settlement value that diverges from both independent sources => `dirty`
(this is exactly the corrupted-actuals failure mode that motivated Phase 0). Missing
CLI or too few sources => `unverifiable`.

This validator does NOT trust the curated station map: a wrong station mapping
surfaces as systematic disagreement and is flagged, not silently accepted.

Run:
    python -m validation.v1_actuals
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.io import CONFIG, cache_path, utcnow_iso, write_report
from validation._http import Http

IEM_CLI = "https://mesonet.agron.iastate.edu/json/cli.py"
IEM_DAILY = "https://mesonet.agron.iastate.edu/cgi-bin/request/daily.py"
NCEI = "https://www.ncei.noaa.gov/access/services/data/v1"

RANGE_F = (-70.0, 145.0)   # physically plausible CONUS bounds
TOL_F = 1.0                # <=1 degF: rounding/method, explained; >=2: flagged


def _as_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _f(x) -> Optional[float]:
    if x in (None, "", "M", "None", "T", "NA"):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_window() -> Tuple[date, date, float]:
    w = yaml.safe_load(open(CONFIG / "windows.yaml"))
    s = _as_date(w["validation_sample"]["start"])
    e = _as_date(w["validation_sample"]["end"])
    minc = float(w.get("gate", {}).get("min_clean_coverage_pct", 95))
    return s, e, minc


def load_curated() -> List[dict]:
    return yaml.safe_load(open(CONFIG / "station_candidates.yaml")).get("cities", [])


def load_unresolved() -> List[str]:
    p = CONFIG / "cities.yaml"
    if not p.exists():
        return []
    doc = yaml.safe_load(open(p)) or {}
    return [c.get("city") for c in doc.get("cities", [])
            if (c.get("station") or {}).get("status") == "unresolved"]


# --------------------------------------------------------------------------- #
# source fetchers
# --------------------------------------------------------------------------- #
def fetch_cli(http: Http, station: str, s: date, e: date) -> Dict[date, Dict[str, Any]]:
    out: Dict[date, Dict[str, Any]] = {}
    for year in range(s.year, e.year + 1):
        j = http.json(IEM_CLI, station=station, year=year)
        for r in j.get("results", []):
            d = _as_date(r["valid"])
            if s <= d <= e:
                hi, lo = _f(r.get("high")), _f(r.get("low"))
                if hi is not None or lo is not None:
                    out[d] = {"high": hi, "low": lo, "name": r.get("name"), "wfo": r.get("wfo")}
    return out


def fetch_metar(http: Http, network: str, station: str, s: date, e: date) -> Dict[date, Dict[str, Any]]:
    txt = http.text(IEM_DAILY, network=network, stations=station,
                    year1=s.year, month1=s.month, day1=s.day,
                    year2=e.year, month2=e.month, day2=e.day, format="comma")
    out: Dict[date, Dict[str, Any]] = {}
    lines = [ln for ln in txt.strip().splitlines() if ln.strip()]
    if not lines:
        return out
    hdr = {k: i for i, k in enumerate(lines[0].split(","))}
    if "day" not in hdr:
        return out
    for ln in lines[1:]:
        c = ln.split(",")
        try:
            d = _as_date(c[hdr["day"]])
        except Exception:
            continue
        out[d] = {"max": _f(c[hdr["max_temp_f"]]), "min": _f(c[hdr["min_temp_f"]])}
    return out


def fetch_ghcn(http: Http, ghcn_id: str, s: date, e: date) -> Dict[date, Dict[str, Any]]:
    j = http.json(NCEI, dataset="daily-summaries", stations=ghcn_id,
                  startDate=s.isoformat(), endDate=e.isoformat(),
                  dataTypes="TMAX,TMIN", units="standard", format="json")
    out: Dict[date, Dict[str, Any]] = {}
    for r in (j if isinstance(j, list) else []):
        d = _as_date(r["DATE"])
        out[d] = {"tmax": _f(r.get("TMAX")), "tmin": _f(r.get("TMIN"))}
    return out


# --------------------------------------------------------------------------- #
# per-day reconciliation
# --------------------------------------------------------------------------- #
def reconcile_day(cli: Optional[dict], metar: Optional[dict],
                  ghcn: Optional[dict]) -> Tuple[str, List[str], Dict[str, Any]]:
    maxes = {"cli": (cli or {}).get("high"), "metar": (metar or {}).get("max"),
             "ghcn": (ghcn or {}).get("tmax")}
    mins = {"cli": (cli or {}).get("low"), "metar": (metar or {}).get("min"),
            "ghcn": (ghcn or {}).get("tmin")}
    flags: List[str] = []

    impossible = False
    for src in ("cli", "metar", "ghcn"):
        mx, mn = maxes[src], mins[src]
        if mx is not None and not (RANGE_F[0] <= mx <= RANGE_F[1]):
            flags.append(f"{src}_max_out_of_range:{mx}"); impossible = True
        if mn is not None and not (RANGE_F[0] <= mn <= RANGE_F[1]):
            flags.append(f"{src}_min_out_of_range:{mn}"); impossible = True
        if mx is not None and mn is not None and mx < mn:
            flags.append(f"{src}_max_lt_min"); impossible = True

    pmax = {k: v for k, v in maxes.items() if v is not None}
    pmin = {k: v for k, v in mins.items() if v is not None}
    smax = (max(pmax.values()) - min(pmax.values())) if len(pmax) >= 2 else None
    smin = (max(pmin.values()) - min(pmin.values())) if len(pmin) >= 2 else None

    if smax == 1:
        flags.append("max_diff_1F_rounding")
    if smin == 1:
        flags.append("min_diff_1F_rounding")
    if smax is not None and smax >= 2:
        flags.append(f"max_disagree_{smax:.0f}F")
    if smin is not None and smin >= 2:
        flags.append(f"min_disagree_{smin:.0f}F")

    disagree = (smax is not None and smax >= 2) or (smin is not None and smin >= 2)
    cli_ok = maxes["cli"] is not None and mins["cli"] is not None
    cross = len(pmax) >= 2 and len(pmin) >= 2

    if impossible or disagree:
        verdict = "dirty"
    elif cli_ok and cross and (smax is not None and smax <= TOL_F) and (smin is not None and smin <= TOL_F):
        verdict = "clean"
    else:
        verdict = "unverifiable"

    detail = {"max": maxes, "min": mins, "spread_max": smax, "spread_min": smin}
    return verdict, flags, detail


# --------------------------------------------------------------------------- #
# per-city + driver
# --------------------------------------------------------------------------- #
def validate_city(http: Http, city: dict, s: date, e: date, minc: float) -> dict:
    cli = fetch_cli(http, city["cli_station"], s, e)
    metar = fetch_metar(http, city["iem_network"], city["iem_station"], s, e)
    ghcn = fetch_ghcn(http, city["ghcn_id"], s, e)

    cache_path("actuals", f"{city['cli_station']}_cli.json").write_text(
        json.dumps({d.isoformat(): v for d, v in cli.items()}, indent=2))

    days = [s + timedelta(days=i) for i in range((e - s).days + 1)]
    counts = {"clean": 0, "dirty": 0, "unverifiable": 0}
    flag_counts: Dict[str, int] = {}
    dirty_days: List[dict] = []
    sources_present = {"cli": 0, "metar": 0, "ghcn": 0}

    for d in days:
        cd, md, gd = cli.get(d), metar.get(d), ghcn.get(d)
        sources_present["cli"] += cd is not None
        sources_present["metar"] += md is not None
        sources_present["ghcn"] += gd is not None
        verdict, flags, detail = reconcile_day(cd, md, gd)
        counts[verdict] += 1
        for fl in flags:
            key = fl.split(":")[0]
            flag_counts[key] = flag_counts.get(key, 0) + 1
        if verdict == "dirty":
            dirty_days.append({"date": d.isoformat(), "flags": flags, "detail": detail})

    total = len(days)
    clean_cov = 100.0 * counts["clean"] / total if total else 0.0
    gate = "PASS" if (clean_cov >= minc and counts["dirty"] == 0) else "FAIL"
    return {
        "city": city["city"], "confidence": city.get("confidence"),
        "stations": {k: city.get(k) for k in ("cli_station", "iem_station", "iem_network", "ghcn_id")},
        "cli_station_name": next(iter(cli.values()), {}).get("name") if cli else None,
        "n_days": total, **counts, "clean_coverage_pct": round(clean_cov, 2),
        "sources_present": sources_present, "flag_counts": flag_counts,
        "dirty_days": dirty_days[:25], "gate": gate,
    }


def run(min_interval: float = 0.25) -> dict:
    s, e, minc = load_window()
    http = Http(min_interval=min_interval)
    cities = load_curated()
    results = [validate_city(http, c, s, e, minc) for c in cities]

    gate_reasons = []
    for r in results:
        if r["gate"] != "PASS":
            gate_reasons.append(f"{r['city']}: cov {r['clean_coverage_pct']}% / dirty {r['dirty']}")
    if not cities:
        gate_reasons.append("no curated cities to validate")
    gate = "PASS" if not gate_reasons else "FAIL"

    payload = {
        "validator": "V1_actuals", "generated_at": utcnow_iso(),
        "window": {"start": s.isoformat(), "end": e.isoformat(), "days": (e - s).days + 1},
        "tolerance_F": TOL_F, "min_clean_coverage_pct": minc,
        "cities": results,
        "unresolved_cities": load_unresolved(),
        "gate": gate, "gate_reasons": gate_reasons,
    }
    write_report("validation/v1_actuals", payload, md_summary=_md(payload))
    print(f"[V1 actuals] window {s}..{e} ({payload['window']['days']}d), "
          f"{len(cities)} curated cities, GATE={gate}")
    for r in results:
        print(f"   {r['city']:<26} clean={r['clean']:<3} dirty={r['dirty']:<2} "
              f"unverif={r['unverifiable']:<3} cov={r['clean_coverage_pct']}%  [{r['gate']}]")
    if gate_reasons:
        print("  reasons:", "; ".join(gate_reasons))
    print(f"   ({len(payload['unresolved_cities'])} discovered cities still station-unresolved)")
    return payload


def _md(p: dict) -> str:
    lines = [f"# V1 — Actuals validator (CLI vs METAR vs GHCN)\n",
             f"_generated {p['generated_at']}_\n",
             f"**GATE: {p['gate']}**" + ("" if p["gate"] == "PASS"
                                         else "  \nreasons: " + "; ".join(p["gate_reasons"])),
             f"\nwindow {p['window']['start']}..{p['window']['end']} "
             f"({p['window']['days']}d), tolerance {p['tolerance_F']}degF, "
             f"min clean coverage {p['min_clean_coverage_pct']}%\n",
             "| city | clean | dirty | unverif | coverage | gate |",
             "|------|------:|------:|--------:|---------:|------|"]
    for r in p["cities"]:
        lines.append(f"| {r['city']} | {r['clean']} | {r['dirty']} | {r['unverifiable']} "
                     f"| {r['clean_coverage_pct']}% | {r['gate']} |")
    lines.append(f"\n_{len(p['unresolved_cities'])} discovered cities still station-unresolved "
                 f"(excluded from gate): {', '.join(p['unresolved_cities'][:12])}"
                 + ("..." if len(p['unresolved_cities']) > 12 else "") + "_")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    payload = run()
    return 0 if payload["gate"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
