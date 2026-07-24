"""Offline unit tests for q43_perp_binary_consistency_probe (Q43 prep infrastructure).

Q43 is GATED on >=7 forward days of tape/perp_tape/ coverage (only 4 file-shaped days exist as
of 2026-07-20). This probe is built + offline-tested now (idle-run policy (b), mirroring
q32/q36) so it fires the day the gate opens. NO network anywhere: every fixture is synthetic
(hand-built joined records or tmp JSONL day-files). These tests cover the four mandated cases:
the insufficient-data self-activation path, the lead-lag leave-one-out recompute on a 2-shock
fixture (L57), the coherence fee+depth+duration gate (a sub-second burst REJECTED, a sustained
>=60s run PASSED), and the BTC/ETH-only join intersection.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.q43_perp_binary_consistency_probe import (
    MIN_CAPTURES_PER_DAY_ADVISORY,
    PERP_DAYS_REQUIRED,
    _perp_capture_density,
    _thin_days,
    binary_implied_level,
    build_coherence_runs,
    classify_member,
    hour_token_from_event,
    join_snapshots,
    lead_lag,
    load_binary_snapshots,
    load_perp_bbo,
    loo_min_abs_rho,
    pearson,
    perp_symbol_from_ticker,
    run_probe,
)

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# small parse helpers
# --------------------------------------------------------------------------- #
def test_perp_symbol_from_ticker():
    assert perp_symbol_from_ticker("KXBTCPERP") == "BTC"
    assert perp_symbol_from_ticker("KXETHPERP") == "ETH"
    assert perp_symbol_from_ticker("KXSOLPERP") == "SOL"
    assert perp_symbol_from_ticker("BTC") is None
    assert perp_symbol_from_ticker(None) is None


def test_hour_token_from_event():
    assert hour_token_from_event("KXBTC-26JUL1921") == "26JUL1921"
    assert hour_token_from_event("KXBTC-26JUL1921-B71750") == "26JUL1921"
    assert hour_token_from_event("NODASH") is None
    assert hour_token_from_event(None) is None


def test_pearson_basic_and_undefined():
    assert pearson([1, 2, 3], [1, 2, 3]) == 1.0
    assert abs(pearson([1, 2, 3], [3, 2, 1]) + 1.0) < 1e-12
    assert pearson([1, 2], [1, 2]) is None          # < 3 points
    assert pearson([1, 1, 1], [1, 2, 3]) is None     # zero variance -> honest None


def test_binary_implied_level_weighted_mean():
    members = [
        {"strike_type": "between", "floor_strike": 100, "cap_strike": 200, "yes_ask": 0.0},
        {"strike_type": "between", "floor_strike": 200, "cap_strike": 300, "yes_ask": 0.5},
        {"strike_type": "between", "floor_strike": 300, "cap_strike": 400, "yes_ask": 0.0},
    ]
    # only the middle member carries weight -> level == its coord (250)
    assert binary_implied_level(members, bracket_sum=0.5) == 250.0
    assert binary_implied_level(members, bracket_sum=0.0) is None   # bad bracket_sum -> None
    assert binary_implied_level([], bracket_sum=1.0) is None


# --------------------------------------------------------------------------- #
# (A) insufficient-data self-activation path
# --------------------------------------------------------------------------- #
def _write_jsonl(path: Path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def test_insufficient_data_path(tmp_path):
    """Below PERP_DAYS_REQUIRED forward days, run_probe returns INSUFFICIENT DATA and runs NO
    analysis (no lead_lag / coherence keys) — the self-activation gate."""
    perp_dir = tmp_path / "perp"
    perp_dir.mkdir()
    for i in range(4):   # 4 < 7
        _write_jsonl(perp_dir / f"dt=2026-07-{17 + i}.jsonl", [{"record_type": "markets"}])
    crypto_glob = str(tmp_path / "crypto" / "dt=*.jsonl")
    rep = run_probe(str(perp_dir / "dt=*.jsonl"), crypto_glob)
    assert rep["status"] == "INSUFFICIENT DATA"
    assert rep["perp_days_available"] == 4
    assert rep["perp_days_required"] == PERP_DAYS_REQUIRED
    assert "lead_lag" not in rep and "coherence" not in rep
    # capture-density readout travels even below the day-count gate (2026-07-23 follow-up)
    assert rep["min_captures_per_day_advisory"] == MIN_CAPTURES_PER_DAY_ADVISORY
    assert set(rep["capture_density_by_day"]) == {f"dt=2026-07-{17 + i}" for i in range(4)}
    # fixture records carry no captured_at/capture_id -> density 0, all days thin
    assert all(n == 0 for n in rep["capture_density_by_day"].values())
    assert sorted(rep["thin_days"]) == sorted(rep["capture_density_by_day"])


# --------------------------------------------------------------------------- #
# (A2) capture-density advisory floor (2026-07-23, idle-run policy (b) follow-up)
# --------------------------------------------------------------------------- #
def test_perp_capture_density_counts_distinct_captures(tmp_path):
    """Density is per-DAY distinct `captured_at` count, not line count — duplicate/append-only
    re-writes of the same capture must not inflate the density read."""
    perp_dir = tmp_path / "perp"
    perp_dir.mkdir()
    _write_jsonl(perp_dir / "dt=2026-07-17.jsonl", [
        {"record_type": "markets", "captured_at": "2026-07-17T00:00:00+00:00"},
        {"record_type": "markets", "captured_at": "2026-07-17T00:00:00+00:00"},  # dup capture
        {"record_type": "markets", "captured_at": "2026-07-17T01:00:00+00:00"},
    ])
    _write_jsonl(perp_dir / "dt=2026-07-18.jsonl", [])
    density = _perp_capture_density(str(perp_dir / "dt=*.jsonl"))
    assert density == {"dt=2026-07-17": 2, "dt=2026-07-18": 0}


def test_thin_days_below_advisory_floor():
    density = {"dt=2026-07-17": 31, "dt=2026-07-19": 6, "dt=2026-07-20": 7}
    assert _thin_days(density, floor=10) == ["dt=2026-07-19", "dt=2026-07-20"]
    assert _thin_days(density, floor=5) == []


# --------------------------------------------------------------------------- #
# (B) lead-lag leave-one-out on a 2-shock fixture (L57)
# --------------------------------------------------------------------------- #
def test_loo_single_shock_collapses_rho():
    """A correlation manufactured by ONE shock tick over an otherwise-uncorrelated base: the
    full rho is near +1, but dropping that single pair collapses |rho| to ~0. loo_min_abs_rho
    must identify the shock (index 4) and report the collapsed recompute (L57)."""
    xs = [1.0, -1.0, 1.0, -1.0, 20.0]   # base (idx 0-3) is uncorrelated with ys; idx4 is the shock
    ys = [1.0, 1.0, -1.0, -1.0, 20.0]
    full = pearson(xs, ys)
    assert full is not None and full > 0.9
    idx, loo = loo_min_abs_rho(xs, ys)
    assert idx == 4
    assert abs(loo) < 1e-9   # the "lead" was one shock tick, not a persistent relationship


def test_loo_too_few_points_returns_none():
    assert loo_min_abs_rho([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == (None, None)


def test_lead_lag_reports_loo_beside_every_rho():
    """lead_lag must attach a leave-one-out recompute to every direction's raw rho (contemp,
    perp_leads, binary_leads) so a single-shock lead can never be reported without its LOO."""
    base = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)

    def snap(dt_min, perp, binlvl):
        return {"symbol": "BTC", "event_ticker": "KXBTC-26JUL1921",
                "captured_at": base + timedelta(minutes=dt_min), "close_utc": None,
                "ttc_seconds": None, "perp_implied": perp, "binary_level": binlvl,
                "spacing": 100.0, "members": []}

    # one event with 6 ordered snapshots -> 5 consecutive change pairs
    perp_levels = [100.0, 101.0, 100.0, 101.0, 100.0, 140.0]
    bin_levels = [100.0, 101.0, 99.0, 101.0, 99.0, 140.0]
    snaps = [snap(i, p, b) for i, (p, b) in enumerate(zip(perp_levels, bin_levels))]
    joined = {"KXBTC-26JUL1921": snaps}
    ll = lead_lag(joined)
    for key in ("contemporaneous", "perp_leads", "binary_leads"):
        assert key in ll
        assert "rho" in ll[key] and "loo_rho" in ll[key] and "loo_dropped_index" in ll[key]
    assert ll["dominant_lead_direction"] in ("perp_leads", "binary_leads")


# --------------------------------------------------------------------------- #
# (C) coherence fee + depth + duration gate
# --------------------------------------------------------------------------- #
def _coh_snap(event, captured_at, perp_implied, member):
    """A joined snapshot near expiry (ttc within the near-expiry window) carrying one member."""
    close = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)
    return {"symbol": "BTC", "event_ticker": event, "captured_at": captured_at,
            "close_utc": close, "ttc_seconds": (close - captured_at).total_seconds(),
            "perp_implied": perp_implied, "binary_level": None, "spacing": 100.0,
            "members": [member]}


def _far_member(ticker, no_ask, no_depth):
    """A bracket far BELOW the perp-implied price -> perp says near-impossible -> buy NO."""
    return {"ticker": ticker, "strike_type": "between", "floor_strike": 64200,
            "cap_strike": 64299.99, "yes_ask": 0.02, "no_ask": no_ask,
            "yes_ask_depth": None, "no_ask_depth": no_depth}


def test_classify_member_no_out_and_neither():
    far = _far_member("M", no_ask=0.90, no_depth=50.0)
    hit = classify_member(far, perp_implied=64550.0, spacing=100.0)
    assert hit is not None and hit["direction"] == "no_out"
    assert hit["price"] == 0.90 and hit["depth"] == 50.0 and hit["edge_after_fee"] > 0
    # perp sits inside the narrow band -> neither certain nor impossible by a full spacing
    assert classify_member(far, perp_implied=64250.0, spacing=100.0) is None
    # a NO ask too rich to clear the fee floor -> not a violation
    assert classify_member(_far_member("M", 0.999, 50.0), 64550.0, 100.0) is None


def test_coherence_burst_rejected_sustained_passed():
    """The binding DEPTH x DURATION gate in wall-clock seconds (L76/L93): a sub-second burst of
    fee-clearing, deep-enough dislocations is NOT executable; a >=60s sustained run IS."""
    base = datetime(2026, 7, 20, 0, 55, tzinfo=UTC)   # ~5min to close -> near-expiry
    perp = 64550.0

    # BURST event: 3 snaps 0.3s apart -> summed wall-clock 0.6s < 60s floor -> rejected
    burst = [
        _coh_snap("BURST", base, perp, _far_member("X", 0.90, 50.0)),
        _coh_snap("BURST", base + timedelta(seconds=0.3), perp, _far_member("X", 0.90, 50.0)),
        _coh_snap("BURST", base + timedelta(seconds=0.6), perp, _far_member("X", 0.90, 50.0)),
    ]
    # SUSTAINED event: 3 snaps 40s apart -> summed 80s >= 60s floor -> executable
    sus = [
        _coh_snap("SUST", base, perp, _far_member("Y", 0.90, 50.0)),
        _coh_snap("SUST", base + timedelta(seconds=40), perp, _far_member("Y", 0.90, 50.0)),
        _coh_snap("SUST", base + timedelta(seconds=80), perp, _far_member("Y", 0.90, 50.0)),
    ]
    joined = {"BURST": burst, "SUST": sus}
    co = build_coherence_runs(joined, duration_floor_seconds=60.0, depth_floor=10.0)
    assert co["n_fee_clearing_dislocations"] == 6
    assert co["n_depth_ok"] == 6
    assert co["n_executable_runs"] == 1
    assert co["executable_runs"][0]["member"] == "Y"
    assert co["executable_runs"][0]["seconds"] >= 60.0


def test_coherence_depth_unmeasurable_and_below_floor_excluded():
    """A fee-clearing dislocation with NO at-touch depth (crypto_hourly carries none) is
    DEPTH-UNMEASURABLE and never a hit; one below the 10-contract floor is likewise excluded.
    Neither produces an executable run — the honest pt1 discipline (a nominal edge is not a
    fill)."""
    base = datetime(2026, 7, 20, 0, 55, tzinfo=UTC)
    perp = 64550.0
    # depth None (unmeasurable) sustained 80s -> still NOT executable
    unmeas = [
        _coh_snap("UNMEAS", base, perp, _far_member("U", 0.90, None)),
        _coh_snap("UNMEAS", base + timedelta(seconds=80), perp, _far_member("U", 0.90, None)),
    ]
    # depth 5 (< 10 floor) sustained -> NOT executable
    thin = [
        _coh_snap("THIN", base, perp, _far_member("T", 0.90, 5.0)),
        _coh_snap("THIN", base + timedelta(seconds=80), perp, _far_member("T", 0.90, 5.0)),
    ]
    co = build_coherence_runs({"UNMEAS": unmeas, "THIN": thin},
                              duration_floor_seconds=60.0, depth_floor=10.0)
    assert co["n_fee_clearing_dislocations"] == 4
    assert co["n_depth_unmeasurable"] == 2
    assert co["n_depth_ok"] == 0
    assert co["n_executable_runs"] == 0


def test_coherence_far_from_expiry_excluded():
    """A dislocation NOT within the near-expiry window is out of scope for the coherence leg."""
    far_dt = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)   # ~13h before close -> not near-expiry
    snap = _coh_snap("FAR", far_dt, 64550.0, _far_member("F", 0.90, 50.0))
    co = build_coherence_runs({"FAR": [snap]}, near_expiry_seconds=1800.0)
    assert co["n_fee_clearing_dislocations"] == 0
    assert co["n_executable_runs"] == 0


# --------------------------------------------------------------------------- #
# (D) BTC/ETH-only join intersection
# --------------------------------------------------------------------------- #
def _perp_entry(symbol, dt, implied):
    return {"captured_at": dt, "capture_id": "c", "symbol": symbol, "bid": 1.0, "ask": 1.0,
            "mid": 1.0, "contract_size": 1.0, "implied_underlying": implied, "mark": None}


def _bin_snap(symbol, dt, level=100.0):
    return {"captured_at": dt, "capture_id": "c", "symbol": symbol,
            "event_ticker": f"KX{symbol}-26JUL1921", "close_utc": None, "bracket_sum": 1.0,
            "spacing": 100.0, "members": [], "implied_level": level}


def test_join_intersection_is_btc_eth_only():
    """The perp covers many symbols (BTC/ETH/SOL here); the binaries cover only BTC/ETH. The
    joinable set is the INTERSECTION — SOL has no binary ladder and is dropped."""
    dt = datetime(2026, 7, 20, 0, 55, tzinfo=UTC)
    perp = [_perp_entry("BTC", dt, 64550.0), _perp_entry("ETH", dt, 3200.0),
            _perp_entry("SOL", dt, 180.0)]
    binary = [_bin_snap("BTC", dt), _bin_snap("ETH", dt)]
    joined_by_event, meta = join_snapshots(perp, binary)
    assert meta["joinable_symbols"] == ["BTC", "ETH"]
    assert "SOL" in meta["perp_symbols"]
    assert "SOL" not in meta["binary_symbols"]
    assert meta["n_joined"] == 2


def test_join_binary_only_subset():
    """If binaries carry only BTC, the joinable set narrows to {BTC} even though ETH exists on
    the perp — the intersection, not the union."""
    dt = datetime(2026, 7, 20, 0, 55, tzinfo=UTC)
    perp = [_perp_entry("BTC", dt, 64550.0), _perp_entry("ETH", dt, 3200.0)]
    binary = [_bin_snap("BTC", dt)]
    _, meta = join_snapshots(perp, binary)
    assert meta["joinable_symbols"] == ["BTC"]
    assert meta["n_joined"] == 1


def test_join_skew_window_excludes_far_perp():
    """A perp BBO outside the +/-max_skew window is not a contemporaneous match."""
    dt = datetime(2026, 7, 20, 0, 55, tzinfo=UTC)
    perp = [_perp_entry("BTC", dt + timedelta(seconds=600), 64550.0)]   # 10min away
    binary = [_bin_snap("BTC", dt)]
    _, meta = join_snapshots(perp, binary, max_skew_seconds=300.0)
    assert meta["n_joined"] == 0
    assert meta["n_dropped_no_perp_in_window"] == 1


# --------------------------------------------------------------------------- #
# (E) end-to-end analysis path through the real loaders (gate open)
# --------------------------------------------------------------------------- #
def test_analysis_path_fires_when_gate_open(tmp_path):
    """With >=7 perp day-files, run_probe crosses the gate and runs both legs through the real
    loaders; the loaders keep only BTC/ETH and the join reports the intersection. Also exercises
    load_perp_bbo's filter to the binary-joinable symbols."""
    perp_dir = tmp_path / "perp"
    crypto_dir = tmp_path / "crypto"
    perp_dir.mkdir()
    crypto_dir.mkdir()

    def markets_rec(ts_iso):
        return {"record_type": "markets", "capture_id": ts_iso, "captured_at": ts_iso,
                "contracts": [
                    {"ticker": "KXBTCPERP", "bid": 6.4536, "ask": 6.4561, "contract_size": 0.0001,
                     "settlement_mark_price": {"price": "6.4519"}},
                    {"ticker": "KXETHPERP", "bid": 1.8717, "ask": 1.8721, "contract_size": 0.001,
                     "settlement_mark_price": {"price": "1.8710"}},
                    # a perp-only symbol the loader must drop (not in BINARY_SYMBOLS)
                    {"ticker": "KXSOLPERP", "bid": 1.80, "ask": 1.81, "contract_size": 0.01,
                     "settlement_mark_price": {"price": "1.805"}},
                ]}

    # seven day-files so the gate opens; the two overlapping captures live in one of them
    ts_a = "2026-07-20T00:50:00+00:00"
    ts_b = "2026-07-20T00:55:00+00:00"
    _write_jsonl(perp_dir / "dt=2026-07-20.jsonl", [markets_rec(ts_a), markets_rec(ts_b)])
    for i in range(6):
        _write_jsonl(perp_dir / f"dt=2026-07-{14 + i}.jsonl", [markets_rec(ts_a)])

    def crypto_rec(ts_iso):
        return {"symbol": "BTC", "capture_id": ts_iso, "captured_at": ts_iso,
                "spot": {"price": 64536.0},
                "current": {"event_ticker": "KXBTC-26JUL1921", "bracket_sum": 1.0,
                            "outcomes": [
                                {"ticker": "KXBTC-26JUL1921-B64550", "strike_type": "between",
                                 "floor_strike": 64500, "cap_strike": 64599.99,
                                 "yes_ask": 0.5, "no_ask": 0.5},
                                {"ticker": "KXBTC-26JUL1921-B64650", "strike_type": "between",
                                 "floor_strike": 64600, "cap_strike": 64699.99,
                                 "yes_ask": 0.5, "no_ask": 0.5},
                            ]}}
    _write_jsonl(crypto_dir / "dt=2026-07-20.jsonl", [crypto_rec(ts_a), crypto_rec(ts_b)])

    perp_glob = str(perp_dir / "dt=*.jsonl")
    crypto_glob = str(crypto_dir / "dt=*.jsonl")

    # loader keeps only BTC/ETH (SOL dropped at load time)
    perp_bbo = load_perp_bbo(perp_glob)
    assert {p["symbol"] for p in perp_bbo} == {"BTC", "ETH"}
    bins = load_binary_snapshots(crypto_glob)
    assert bins and bins[0]["close_utc"] is not None   # ET token parsed to a UTC close

    rep = run_probe(perp_glob, crypto_glob)
    assert rep["status"] == "ANALYSIS"
    assert rep["join_meta"]["joinable_symbols"] == ["BTC"]   # binaries only carry BTC here
    assert "lead_lag" in rep and "coherence" in rep
    # every fixture day here carries exactly 1 capture -> all 7 are thin, and the ANALYSIS-path
    # note carries the caveat forward rather than silently dropping it once the gate opens
    assert len(rep["thin_days"]) == 7
    assert "CAVEAT" in rep["note"] and "calendar-gate-open" in rep["note"]


# --------------------------------------------------------------------------- #
# (F) multiplexed-record_type consumer-correctness (2026-07-24 idle-run audit)
# --------------------------------------------------------------------------- #
def test_load_perp_bbo_ignores_non_markets_records(tmp_path):
    """perp_tape multiplexes 4 record types (markets / orderbook / funding_estimate /
    funding_rates) that legitimately SHARE (ticker, captured_at) within one pass. A 2026-07-24
    idle-run audit confirmed all three current perp consumers filter record_type, but nothing
    pinned load_perp_bbo's filter against an adversarial non-markets row. An `orderbook` /
    `funding_estimate` record carrying a top-level perp ticker (and, worst-case, a bogus
    `contracts` list with a DIFFERENT quote) must NEVER produce a BBO -- only the `markets`
    record's contracts do. Guards the ONLY gate-open item's correctness against a future refactor
    that starts reading BBO from a non-markets record (an L96-class conflation)."""
    perp_dir = tmp_path / "perp"
    perp_dir.mkdir()
    ts = "2026-07-24T00:29:58+00:00"
    markets = {"record_type": "markets", "capture_id": ts, "captured_at": ts,
               "contracts": [{"ticker": "KXBTCPERP", "bid": 6.4536, "ask": 6.4561,
                              "contract_size": 0.0001,
                              "settlement_mark_price": {"price": "6.4519"}}]}
    # adversarial: a non-markets record for the SAME ticker+captured_at, carrying a bogus
    # contracts list with a DIFFERENT quote -- must be ignored purely on record_type.
    orderbook = {"record_type": "orderbook", "ticker": "KXBTCPERP", "capture_id": ts,
                 "captured_at": ts, "asks": [[6.99, 10]], "bids": [[6.00, 10]],
                 "contracts": [{"ticker": "KXBTCPERP", "bid": 6.00, "ask": 6.99,
                                "contract_size": 0.0001,
                                "settlement_mark_price": {"price": "6.50"}}]}
    funding = {"record_type": "funding_estimate", "ticker": "KXBTCPERP", "capture_id": ts,
               "captured_at": ts, "mark_price": 6.45, "funding_rate_estimate": 0.0}
    _write_jsonl(perp_dir / "dt=2026-07-24.jsonl", [orderbook, markets, funding])

    bbo = load_perp_bbo(str(perp_dir / "dt=*.jsonl"))
    assert len(bbo) == 1                        # exactly one BTC BBO, from the markets record only
    assert bbo[0]["symbol"] == "BTC"
    # the markets quote, NOT the orderbook record's bogus 6.00/6.99
    assert bbo[0]["bid"] == 6.4536 and bbo[0]["ask"] == 6.4561
