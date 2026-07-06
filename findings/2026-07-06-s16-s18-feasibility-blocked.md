# S16/S18 feasibility check — both BLOCKED on data-adequacy, not effort

`2026-07-06` · research loop · queue items `Q14` (S16), `Q15` (S18)

## Context

With Q1–Q13 all DONE, claimed, or time-blocked (Q7 needs ≥7 days of Q2 tape, eligible
~2026-07-09/10; Q13 needs ≥10 days of Q3 tape, eligible ~2026-07-13), this run picked up the
registry's own stated priority order (`kb/strategies/00-index.md`: "...S15 → S16 → S17 → S18")
and checked the next two un-started candidates. Both hit a real, external, venue-side wall
before any collector code was worth writing. Recording the evidence here so a future run does
not re-spend a milestone rediscovering the same dead ends.

## S16 — FedWatch-anchored shock fade on KXFED

**Claim under test:** CME's FedWatch tool publishes free ZQ-implied Fed-meeting probabilities
that could anchor a fade on Kalshi's KXFED ladder.

**Finding: BLOCKED(fedwatch-scrape).** `cmegroup.com` is behind Akamai-class bot protection —
every request without a full browser/JS challenge is rejected:

```
GET https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html   (HTTP/2)  -> stream reset (INTERNAL_ERROR)
GET https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html   (HTTP/1.1, browser UA) -> 403
GET https://www.cmegroup.com/                                                (HTTP/1.1, browser UA) -> 403
GET https://www.cmegroup.com/CmeWS/exp/fedwatch/index.html                                          -> 403
GET https://www.cmegroup.com/services/fedwatch                                                      -> 403
GET https://www.cmegroup.com/CmeWS/mvc/Volume/V1/Fedwatch                                            -> 403
```

Control check (egress is fine in general this run, so the 403s are venue-side): Kalshi's own
API returned 200, and Q10's Atlanta Fed GDPNow scrape (a structurally similar "free JS-embedded
data on a public page" target) is confirmed working in production. CME specifically walls
non-browser clients — the same shape that already blocked Cleveland Fed's CPI-nowcast page
(Q10). A headless-browser scrape that solves a bot challenge is not something an unattended
hourly cloud collector should depend on (fragile, and arguably against the target site's terms).
**No further collector work is justified until a free, non-bot-walled FedWatch data source is
found.**

## S18 — Single-poll overreaction fade (Congress-control markets)

**Claim under test:** Kalshi's House/Senate control markets plus a free generic-congressional-
ballot polling average could support a single-poll-jump fade.

**Finding: BLOCKED(no-live-market), with a secondary polling-feed blocker.**

Kalshi side — confirmed the series exist but are **empty**:

```
GET /trade-api/v2/series/HOUSE     -> 200, title "US House of Representatives Control"
GET /trade-api/v2/series/SENATE    -> 200, title "US Senate Control"
GET /trade-api/v2/series/KXHOUSE   -> 200, title "US House of Representatives Control"
GET /trade-api/v2/series/KXSENATE  -> 200, title "US Senate Control"

GET /trade-api/v2/markets?series_ticker={HOUSE,SENATE,KXHOUSE,KXSENATE}&status={open,unopened,closed}
    -> n=0 for all 4 tickers × all 3 statuses (12/12 empty)
```

The 2026 midterm control contracts have not been listed yet — there is nothing to snapshot and
no Kalshi print to join a poll against. Unlike Q10/Q12 (settled data actively purging after 60
days — collect-now-or-lose-it), a market that doesn't exist yet has no purge deadline, so there
is no urgency to build a stub collector today.

Polling side — checked anyway, since it's the other half of the gate and worth knowing before
committing to this candidate later:

```
GET https://projects.fivethirtyeight.com/polls/generic-ballot/                            -> 302 -> abcnews.com/politics (dead stub, site retired/migrated)
GET https://projects.fivethirtyeight.com/generic-ballot-data/generic_ballot_averages.csv   -> 302 -> abcnews.com/politics (same dead stub)
GET https://www.natesilver.net/p/silver-bulletin-election-forecast                        -> 302 -> (Substack redirect, no static data endpoint)
GET https://www.realclearpolling.com/polls/generic-congressional-vote                     -> 403 (Akamai-class, same as CME)
```

The classic free 538 CSV feed is gone, not just moved — the redirect lands on a generic ABC News
politics page with no polling data. One live candidate remains: Wikipedia's "2026 United States
House of Representatives elections" article (`en.wikipedia.org`, confirmed HTTP 200 via both the
plain page and `action=parse` API) has a generic-ballot polling section sourced from Silver
Bulletin/VoteHub/Decision Desk HQ. Wikipedia doesn't bot-wall requests, so a wikitable scrape is
plausible — but building it now would produce tape with no Kalshi market to ever join it against.
**Revisit both legs together once Kalshi actually lists `HOUSE`/`SENATE` markets for the 2026
cycle.**

## Takeaway

Both candidates are honest `BLOCKED` verdicts per the Stop rules ("a DEAD verdict is a success")
— not CI falsifications, data-adequacy gaps. No source or test code changed this run; the only
diff is this writeup, the queue additions (`Q14`, `Q15`), and the completed stranded-tape sweep
(see `kb/00-LOG.md` for line counts).
