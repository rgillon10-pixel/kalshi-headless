#!/usr/bin/env python3
"""S20 — Polymarket wallet forensics (READ-ONLY research sprint).

Pre-registration: findings/2026-07-13-polymarket-wallet-forensics-s20-prereg.md
(written BEFORE any wallet data was pulled; council CONDITIONAL 3-0, conditions C1-C5).

Pipeline (subcommands, resumable via JSONL caches under data/s20_wallet_forensics/):
  collect  — leaderboard top-N wallets (30d PnL) + per-wallet fills (takerOnly=false
             AND takerOnly=true; maker fills = set difference of tx hashes per fill key).
  resolve  — join every touched conditionId to its resolution: gamma-api batch first
             (standard markets), CLOB /markets/{cid} fallback (5-min updown family).
             Markets that resolve nowhere are recorded `unjoinable`, never guessed.
  analyze  — pre-registered skill metric: per-trade e_i = sign*(outcome - price),
             UNWEIGHTED mean per wallet, cluster bootstrap BY MARKET (10k resamples),
             one-sided p under H0 mean<=0, Benjamini-Hochberg FDR q=0.10 across ALL
             evaluated wallets. Evaluation set = fills OLDER than the 30d selection
             window when reachable (primary), else first-half-by-time within-window
             fallback (flagged `within-window-split`). n>=100 or `insufficient-n`.

Honest-accounting rules carried from collection/*: every excluded fill lands in a
counted bucket (unjoinable / unresolved / in-selection-window / bad-fields), never
silently dropped. All numbers are tagged polymarket_onchain — NOTHING here is evidence
of Kalshi edge (C5).

Classification taxonomy (C3, operationalized before any per-wallet result was viewed):
thresholds below are fixed constants; see TAXONOMY_THRESHOLDS.
"""
import json
import math
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "s20_wallet_forensics"
DATA.mkdir(parents=True, exist_ok=True)

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

TOP_N = 50
PAGE = 500
MAX_OFFSET = 3000          # empirically the deepest non-empty offset (2026-07-13 probe)
SELECTION_WINDOW_S = 30 * 86400
MIN_EVAL_N = 100           # pre-registered
BOOTSTRAP_N = 10_000       # pre-registered
FDR_Q = 0.10               # pre-registered
MAX_RESOLVE_PER_WALLET = 250  # cluster-sample cap (seeded); logged per wallet — C4 budget
SEED = 20260713

TAXONOMY_THRESHOLDS = {
    "maker_share_passive_mm": 0.50,       # >=50% maker fills -> passive maker / spread capture
    "favorite_harvester_share": 0.50,     # >=50% of fills are favorite-side entries (buy>=0.85 / sell<=0.15)
    "endgame_share": 0.40,                # >=40% of fills are >=0.90 buys in final 24h of market life
    "category_hhi_specialist": 0.50,      # HHI over category shares
    "two_sided_share_arb": 0.30,          # >=30% of markets traded on both outcomes
}

_session_stats = {"calls": 0, "errors": 0, "retries": 0}


def get_json(url, tries=4):
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.4.0", "Accept": "application/json"})
        try:
            _session_stats["calls"] += 1
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None  # hard miss (offset cap / unknown id) — caller records it
            _session_stats["retries"] += 1
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            _session_stats["retries"] += 1
            time.sleep(1.5 * (attempt + 1))
    _session_stats["errors"] += 1
    return None


def fill_key(t):
    # one on-chain tx can carry several fills; key on tx + token + side + size + price
    return (t.get("transactionHash"), t.get("asset"), t.get("side"), str(t.get("size")), str(t.get("price")))


# ---------------------------------------------------------------- collect
def fetch_wallet_fills(wallet, taker_only):
    fills = []
    for offset in range(0, MAX_OFFSET + 1, PAGE):
        url = (f"{DATA_API}/trades?user={wallet}&limit={PAGE}&offset={offset}"
               f"&takerOnly={'true' if taker_only else 'false'}")
        page = get_json(url)
        if not isinstance(page, list) or not page:
            break
        fills.extend(page)
        if len(page) < PAGE:
            break
        time.sleep(0.15)
    return fills


def cmd_collect():
    lb_path = DATA / "leaderboard.json"
    lb = get_json(f"{DATA_API}/v1/leaderboard?window=30d&rankType=pnl&limit={TOP_N}")
    if not isinstance(lb, list) or not lb:
        sys.exit("leaderboard fetch failed — abort (C2 gate)")
    lb_path.write_text(json.dumps({"captured_at": int(time.time()), "window": "30d",
                                   "rankType": "pnl", "rows": lb}, indent=1))
    print(f"leaderboard: {len(lb)} wallets")

    fills_dir = DATA / "fills"
    fills_dir.mkdir(exist_ok=True)

    def one(row):
        w = row["proxyWallet"]
        out = fills_dir / f"{w}.json"
        if out.exists():
            return w, "cached"
        allf = fetch_wallet_fills(w, taker_only=False)
        takf = fetch_wallet_fills(w, taker_only=True)
        taker_keys = {fill_key(t) for t in takf}
        for t in allf:
            t["is_taker"] = fill_key(t) in taker_keys
        out.write_text(json.dumps({"wallet": w, "captured_at": int(time.time()),
                                   "n_all": len(allf), "n_taker_endpoint": len(takf),
                                   "history_capped": len(allf) >= MAX_OFFSET + PAGE,
                                   "fills": allf}))
        return w, f"{len(allf)} fills"

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(one, row): row for row in lb}
        for fut in as_completed(futs):
            w, msg = fut.result()
            print(f"  {w[:10]}… {msg}", flush=True)
    print("collect done:", _session_stats)


# ---------------------------------------------------------------- resolve
def cmd_resolve():
    rng = random.Random(SEED)
    lb = json.loads((DATA / "leaderboard.json").read_text())["rows"]
    now = int(time.time())
    t_split = now - SELECTION_WINDOW_S

    # Per-wallet cluster sample of conditionIds (uniform random, seeded) to bound the
    # resolution budget. Uniform market sampling keeps the mean-e_i estimator unbiased.
    wanted = set()
    sample_log = {}
    for row in lb:
        w = row["proxyWallet"]
        f = DATA / "fills" / f"{w}.json"
        if not f.exists():
            continue
        fills = json.loads(f.read_text())["fills"]
        pre = sorted({t["conditionId"] for t in fills if t["timestamp"] < t_split})
        inw = sorted({t["conditionId"] for t in fills if t["timestamp"] >= t_split})
        take_pre = pre if len(pre) <= MAX_RESOLVE_PER_WALLET else rng.sample(pre, MAX_RESOLVE_PER_WALLET)
        room = max(0, MAX_RESOLVE_PER_WALLET - len(take_pre))
        take_inw = inw if len(inw) <= room else rng.sample(inw, room)
        sample_log[w] = {"pre_total": len(pre), "pre_sampled": len(take_pre),
                         "inwindow_total": len(inw), "inwindow_sampled": len(take_inw)}
        wanted.update(take_pre)
        wanted.update(take_inw)
    (DATA / "resolve_sampling.json").write_text(json.dumps(sample_log, indent=1))
    print(f"unique conditionIds to resolve: {len(wanted)}")

    res_path = DATA / "resolutions.jsonl"
    done = set()
    if res_path.exists():
        for line in res_path.read_text().splitlines():
            done.add(json.loads(line)["conditionId"])
    todo = sorted(wanted - done)
    print(f"already resolved: {len(done)}, todo: {len(todo)}")

    out = res_path.open("a")

    def write(rec):
        out.write(json.dumps(rec) + "\n")

    # pass 1 — gamma batches (repeated condition_ids params, 20 per call)
    still = []
    for i in range(0, len(todo), 20):
        batch = todo[i:i + 20]
        qs = "&".join(f"condition_ids={c}" for c in batch)
        got = get_json(f"{GAMMA_API}/markets?{qs}") or []
        found = {}
        for m in got if isinstance(got, list) else []:
            cid = m.get("conditionId")
            if cid in batch:
                found[cid] = m
        for cid in batch:
            m = found.get(cid)
            if m is None:
                still.append(cid)
                continue
            try:
                outcomes = json.loads(m["outcomes"]) if isinstance(m.get("outcomes"), str) else m.get("outcomes")
                prices = json.loads(m["outcomePrices"]) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices")
            except Exception:
                outcomes, prices = None, None
            write({"conditionId": cid, "source": "gamma", "closed": m.get("closed"),
                   "endDate": m.get("endDate"), "outcomes": outcomes, "outcomePrices": prices,
                   "question": m.get("question")})
        if i % 200 == 0:
            print(f"  gamma {i}/{len(todo)} (fallback queue: {len(still)})", flush=True)
        time.sleep(0.1)
    out.flush()
    print(f"gamma pass done; {len(still)} go to CLOB fallback")

    # pass 2 — CLOB per-market fallback (updown family etc.)
    def clob_one(cid):
        m = get_json(f"{CLOB_API}/markets/{cid}")
        if not isinstance(m, dict) or "tokens" not in m:
            return {"conditionId": cid, "source": "unjoinable"}
        toks = m.get("tokens") or []
        return {"conditionId": cid, "source": "clob", "closed": m.get("closed"),
                "endDate": m.get("end_date_iso"), "question": m.get("question"),
                "outcomes": [t.get("outcome") for t in toks],
                "winners": [bool(t.get("winner")) for t in toks]}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(clob_one, cid) for cid in still]
        for j, fut in enumerate(as_completed(futs)):
            write(fut.result())
            if j % 500 == 0:
                out.flush()
                print(f"  clob {j}/{len(still)}", flush=True)
    out.close()
    print("resolve done:", _session_stats)


# ---------------------------------------------------------------- analyze
def load_resolutions():
    res = {}
    for line in (DATA / "resolutions.jsonl").read_text().splitlines():
        r = json.loads(line)
        res[r["conditionId"]] = r
    return res


def token_outcome_value(fill, r):
    """Resolved value (0/1) of the token this fill traded, or None if not determinable."""
    if r is None or r.get("source") == "unjoinable" or not r.get("closed"):
        return None
    name = fill.get("outcome")
    outcomes = r.get("outcomes") or []
    if r["source"] == "clob":
        winners = r.get("winners") or []
        if name in outcomes and any(winners):
            return 1.0 if winners[outcomes.index(name)] else 0.0
        return None
    prices = r.get("outcomePrices") or []
    if name in outcomes and len(prices) == len(outcomes):
        try:
            v = float(prices[outcomes.index(name)])
        except (TypeError, ValueError):
            return None
        if v in (0.0, 1.0):
            return v
    return None


def category_of(fill):
    slug = (fill.get("slug") or "")
    title = (fill.get("title") or "").lower()
    if "updown" in slug or "up or down" in title:
        return "crypto-updown"
    for kw, cat in [("bitcoin", "crypto"), ("ethereum", "crypto"), ("solana", "crypto"), ("xrp", "crypto"),
                    ("fed ", "macro"), ("rate", "macro"), ("cpi", "macro"), ("inflation", "macro"), ("gdp", "macro"),
                    ("nba", "sports"), ("nfl", "sports"), ("mlb", "sports"), ("ufc", "sports"), (" vs. ", "sports"),
                    (" vs ", "sports"), ("world cup", "sports"), ("wimbledon", "sports"), ("f1", "sports"),
                    ("election", "politics"), ("president", "politics"), ("senate", "politics"), ("mayor", "politics"),
                    ("trump", "politics"), ("congress", "politics")]:
        if kw in title:
            return cat
    return "other"


def bh_fdr(pvals, q):
    """Benjamini-Hochberg: returns set of indices rejected at FDR q."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    keep, thresh_i = set(), -1
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            thresh_i = rank
    for rank, i in enumerate(order, start=1):
        if rank <= thresh_i:
            keep.add(i)
    return keep


def cmd_analyze():
    rng = random.Random(SEED)
    lb = json.loads((DATA / "leaderboard.json").read_text())
    t_capture = lb["captured_at"]
    t_split = t_capture - SELECTION_WINDOW_S
    res = load_resolutions()
    sampling = json.loads((DATA / "resolve_sampling.json").read_text())

    wallets_out = []
    for row in lb["rows"]:
        w = row["proxyWallet"]
        fp = DATA / "fills" / f"{w}.json"
        if not fp.exists():
            continue
        blob = json.loads(fp.read_text())
        fills = blob["fills"]
        acct = {"total": len(fills), "bad-fields": 0, "not-sampled": 0, "unjoinable": 0,
                "unresolved": 0, "pre-window-usable": 0, "in-window-usable": 0}
        pre_edges, inw_edges = [], []   # (conditionId, e_i, fill) tuples
        for t in fills:
            try:
                price = float(t["price"]); side = t["side"]; ts = int(t["timestamp"])
            except (KeyError, TypeError, ValueError):
                acct["bad-fields"] += 1
                continue
            cid = t.get("conditionId")
            if cid not in res:
                acct["not-sampled"] += 1
                continue
            r = res[cid]
            if r.get("source") == "unjoinable":
                acct["unjoinable"] += 1
                continue
            v = token_outcome_value(t, r)
            if v is None:
                acct["unresolved"] += 1
                continue
            sign = 1.0 if side == "BUY" else -1.0
            e = sign * (v - price)
            if ts < t_split:
                acct["pre-window-usable"] += 1
                pre_edges.append((cid, e, t))
            else:
                acct["in-window-usable"] += 1
                inw_edges.append((cid, e, t))

        # evaluation set per pre-registration
        if len(pre_edges) >= MIN_EVAL_N:
            mode, eval_set = "pre-window", pre_edges
        else:
            inw_sorted = sorted(inw_edges, key=lambda x: x[2]["timestamp"])
            half = inw_sorted[: len(inw_sorted) // 2]
            if len(half) >= MIN_EVAL_N:
                mode, eval_set = "within-window-split", half
            else:
                mode, eval_set = "insufficient-n", []

        rec = {"wallet": w, "userName": row.get("userName"), "lb_pnl_30d": row.get("pnl"),
               "lb_vol_30d": row.get("vol"), "mode": mode, "accounting": acct,
               "sampling": sampling.get(w), "history_capped": blob.get("history_capped"),
               "n_eval": len(eval_set), "price_source_tag": "polymarket_onchain"}

        if eval_set:
            clusters = {}
            for cid, e, _t in eval_set:
                clusters.setdefault(cid, []).append(e)
            keys = list(clusters.keys())
            mean_e = sum(e for _c, e, _t in eval_set) / len(eval_set)
            wmean_num = sum(e * float(t["size"]) for _c, e, t in eval_set)
            wden = sum(float(t["size"]) for _c, e, t in eval_set) or 1.0
            boots, le0 = [], 0
            for _ in range(BOOTSTRAP_N):
                tot, cnt = 0.0, 0
                for _k in range(len(keys)):
                    es = clusters[keys[rng.randrange(len(keys))]]
                    tot += sum(es); cnt += len(es)
                bm = tot / cnt if cnt else 0.0
                boots.append(bm)
                if bm <= 0:
                    le0 += 1
            boots.sort()
            rec.update({
                "mean_edge_per_trade": round(mean_e, 6),
                "size_weighted_mean_edge": round(wmean_num / wden, 6),
                "n_markets_eval": len(keys),
                "boot_ci90": [round(boots[int(0.05 * BOOTSTRAP_N)], 6), round(boots[int(0.95 * BOOTSTRAP_N)], 6)],
                "p_one_sided": round(le0 / BOOTSTRAP_N, 6),
            })

            # ------- taxonomy features (C3; computed on ALL usable fills, descriptive)
            allu = pre_edges + inw_edges
            n_u = len(allu)
            takers = [t for _c, _e, t in allu if t.get("is_taker")]
            maker_share = 1.0 - (len(takers) / n_u) if n_u else 0.0
            fav = sum(1 for _c, _e, t in allu
                      if (t["side"] == "BUY" and float(t["price"]) >= 0.85) or
                         (t["side"] == "SELL" and float(t["price"]) <= 0.15))
            both_sides = 0
            per_market_sides = {}
            for _c, _e, t in allu:
                per_market_sides.setdefault(t["conditionId"], set()).add(t.get("outcome"))
            both_sides = sum(1 for s in per_market_sides.values() if len(s) > 1)
            cats = {}
            for _c, _e, t in allu:
                cats[category_of(t)] = cats.get(category_of(t), 0) + 1
            hhi = sum((v / n_u) ** 2 for v in cats.values()) if n_u else 0.0
            rec["features"] = {
                "maker_share": round(maker_share, 4),
                "favorite_side_share": round(fav / n_u, 4) if n_u else None,
                "two_sided_market_share": round(both_sides / len(per_market_sides), 4) if per_market_sides else None,
                "category_mix": {k: round(v / n_u, 4) for k, v in sorted(cats.items(), key=lambda kv: -kv[1])},
                "category_hhi": round(hhi, 4),
            }
            th = TAXONOMY_THRESHOLDS
            labels = []
            if maker_share >= th["maker_share_passive_mm"]:
                labels.append("passive-maker/spread-capture")
            if n_u and fav / n_u >= th["favorite_harvester_share"]:
                labels.append("longshot-favorite-harvester")
            if per_market_sides and both_sides / len(per_market_sides) >= th["two_sided_share_arb"]:
                labels.append("cross-market/two-sided")
            if hhi >= th["category_hhi_specialist"]:
                labels.append(f"specialist:{max(cats, key=cats.get)}")
            rec["taxonomy_labels"] = labels or ["unclassified"]
        wallets_out.append(rec)
        print(f"  {w[:10]}… mode={mode} n_eval={rec['n_eval']} "
              f"mean_e={rec.get('mean_edge_per_trade')} p={rec.get('p_one_sided')}", flush=True)

    evaluated = [r for r in wallets_out if r["mode"] != "insufficient-n"]
    pvals = [r["p_one_sided"] for r in evaluated]
    rejected = bh_fdr(pvals, FDR_Q) if evaluated else set()
    for i, r in enumerate(evaluated):
        r["skilled_fdr10"] = i in rejected
    summary = {
        "captured_at": t_capture, "selection_window_days": 30, "top_n": len(lb["rows"]),
        "wallets_with_fills": len(wallets_out), "evaluated": len(evaluated),
        "insufficient_n": len(wallets_out) - len(evaluated),
        "skilled_at_fdr10": sum(1 for r in evaluated if r["skilled_fdr10"]),
        "pre_window_mode": sum(1 for r in evaluated if r["mode"] == "pre-window"),
        "within_window_split_mode": sum(1 for r in evaluated if r["mode"] == "within-window-split"),
        "price_source_tag": "polymarket_onchain",
        "prereg": "findings/2026-07-13-polymarket-wallet-forensics-s20-prereg.md",
    }
    (DATA / "analysis.json").write_text(json.dumps({"summary": summary, "wallets": wallets_out}, indent=1))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("collect", "all"):
        cmd_collect()
    if cmd in ("resolve", "all"):
        cmd_resolve()
    if cmd in ("analyze", "all"):
        cmd_analyze()
