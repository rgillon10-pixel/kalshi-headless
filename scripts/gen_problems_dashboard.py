#!/usr/bin/env python3
"""Generate a self-contained HTML dashboard of every 'problem' this codebase has
recorded since inception, by parsing the append-only source-of-truth registries:

  kb/lessons/00-lessons.md   -> the lessons ledger (codified bugs / traps / gotchas)
  kb/strategies/00-index.md  -> the strategy registry (hypotheses proven dead / alive)
  kb/00-LOG.md               -> the run log (how findings are read + acted on)

Read-only over the repo; emits one HTML file. Re-run any time to refresh.
"""
import re, html, datetime, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[0]
# Allow running from anywhere: locate repo root by walking up for kb/lessons
def find_repo(start):
    p = pathlib.Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / "kb" / "lessons" / "00-lessons.md").exists():
            return cand
    raise SystemExit("could not locate repo root (kb/lessons/00-lessons.md)")

REPO = find_repo("/Users/ryan.gillon/Active/01-projects/kalshi.headless")
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "reports" / "problems-dashboard.html"

SPLIT = re.compile(r"(?<!\\)\|")  # split table cells on unescaped pipes

def cells(line):
    parts = SPLIT.split(line.strip())
    # drop leading/trailing empties from surrounding pipes
    if parts and parts[0].strip() == "": parts = parts[1:]
    if parts and parts[-1].strip() == "": parts = parts[:-1]
    return [c.strip() for c in parts]

def inline(md):
    """Minimal markdown-inline -> HTML (escape first, then re-inject code/bold)."""
    s = md.replace("\\|", "|")
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: "<strong>" + m.group(1) + "</strong>", s)
    return s

# ---------------------------------------------------------------- lessons
def parse_lessons():
    rows = []
    for line in (REPO / "kb" / "lessons" / "00-lessons.md").read_text().splitlines():
        if re.match(r"^\|\s*L\d+\s*\|", line):
            c = cells(line)
            if len(c) < 5: continue
            lid, date, lesson, source, enf = c[0], c[1], c[2], c[3], c[4]
            # leading bold token or first word of enforcement cell = status
            m = re.search(r"\*\*([^*]+)\*\*", enf)
            token = (m.group(1) if m else enf.split("—")[0]).strip().lower()
            if "unenforced" in token: bucket = "unenforced"
            elif "invariant" in token: bucket = "invariant"
            elif "test" in token: bucket = "test"
            elif "protocol" in token: bucket = "protocol"
            elif "ledger" in token: bucket = "ledger"
            else: bucket = "protocol"
            superseded = bool(re.search(r"supersede", enf, re.I) and "supersedes" in enf.lower())
            rows.append(dict(id=lid, date=date, lesson=lesson, source=source,
                             enf=enf, bucket=bucket))
    return rows

# ---------------------------------------------------------------- strategies
def parse_strategies():
    rows = []
    txt = (REPO / "kb" / "strategies" / "00-index.md").read_text()
    for line in txt.splitlines():
        if re.match(r"^\|\s*\*\*S\d+\*\*\s*\|", line):
            c = cells(line)
            if len(c) < 6: continue
            sid = re.sub(r"\*", "", c[0])
            name, source, status, conf, gate = c[1], c[2], c[3], c[4], c[5]
            st = status.lower()
            if "dead" in st: bucket = "dead"
            elif "built" in st: bucket = "built"
            elif "data-collecting" in st or "collecting" in st: bucket = "collecting"
            elif "gated" in st or "first-cut" in st: bucket = "gated"
            elif "blocked" in st: bucket = "blocked"
            else: bucket = "idea"
            rows.append(dict(id=sid, name=name, source=source, status=status,
                             conf=conf, gate=gate, bucket=bucket))
    return rows

# ---------------------------------------------------------------- log
def parse_log():
    heads = []
    for line in (REPO / "kb" / "00-LOG.md").read_text().splitlines():
        if line.startswith("## "):
            heads.append(line[3:].strip())
    return heads

lessons = parse_lessons()
strategies = parse_strategies()
log_heads = parse_log()

# counts
lb = {}
for r in lessons: lb[r["bucket"]] = lb.get(r["bucket"], 0) + 1
sb = {}
for r in strategies: sb[r["bucket"]] = sb.get(r["bucket"], 0) + 1

now = datetime.date.today().isoformat()

LESSON_LABEL = {
    "invariant": ("Invariant", "CI assertion — the next variant of this bug fails the build"),
    "test": ("Test-pinned", "a regression test pins the specific fix"),
    "protocol": ("Protocol", "encoded in a charter / probe precedent (not statically assertable)"),
    "ledger": ("Ledger-only", "venue/methodology fact — honest terminal state, nothing to assert"),
    "unenforced": ("UNENFORCED", "open — the standing work queue; not yet climbed the gradient"),
}
LESSON_ORDER = ["unenforced", "protocol", "ledger", "test", "invariant"]
S_LABEL = {
    "dead": "Dead ✗ (hypothesis falsified / data-adequacy killed)",
    "collecting": "Data-collecting",
    "gated": "First-cut done · gated",
    "built": "Built ✅ (substrate)",
    "blocked": "Blocked on data",
    "idea": "Idea",
}
S_ORDER = ["dead", "collecting", "gated", "blocked", "idea", "built"]

def lesson_rows_html():
    out = []
    for r in sorted(lessons, key=lambda x: int(x["id"][1:])):
        num = int(r["id"][1:])
        out.append(f"""<tr data-bucket="{r['bucket']}">
  <td class="lid">{r['id']}</td>
  <td class="ldate">{html.escape(r['date'])}</td>
  <td class="ltext">{inline(r['lesson'])}</td>
  <td><span class="pill p-{r['bucket']}">{LESSON_LABEL[r['bucket']][0]}</span></td>
  <td class="lsrc">{inline(r['source'])}</td>
</tr>""")
    return "\n".join(out)

def strat_rows_html():
    out = []
    for r in sorted(strategies, key=lambda x: int(re.sub(r"\D","",x["id"]) or 0)):
        out.append(f"""<tr data-sbucket="{r['bucket']}">
  <td class="sid">{r['id']}</td>
  <td class="sname">{inline(r['name'])}</td>
  <td><span class="pill s-{r['bucket']}">{inline(r['status'])}</span></td>
  <td class="sgate">{inline(r['gate'])}</td>
</tr>""")
    return "\n".join(out)

def chip(label, n, cls):
    return f'<button class="chip {cls}" data-filter="{cls}"><b>{n}</b> {label}</button>'

lesson_chips = "".join(
    chip(LESSON_LABEL[b][0], lb.get(b,0), b) for b in LESSON_ORDER
)
strat_chips = "".join(
    f'<span class="sstat"><b>{sb.get(b,0)}</b> {S_LABEL[b].split(" (")[0]}</span>' for b in S_ORDER if sb.get(b,0)
)

recent_log = "\n".join(
    f'<li>{inline(h)}</li>' for h in log_heads[:18]
)

HTML = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>kalshi.headless — problem ledger since inception</title>
<style>
:root {{
  --bg:#0d1117; --panel:#161b22; --panel2:#1c232c; --bd:#2a323d; --tx:#e6edf3;
  --mut:#8b949e; --acc:#58a6ff;
  --unenforced:#f0883e; --protocol:#a371f7; --ledger:#8b949e; --test:#3fb950; --invariant:#238636;
  --dead:#6e7681; --collecting:#58a6ff; --gated:#d29922; --built:#238636; --blocked:#484f58; --idea:#8b949e;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--tx);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:32px 20px 80px; }}
h1 {{ font-size:26px; margin:0 0 4px; letter-spacing:-.02em; }}
.sub {{ color:var(--mut); margin:0 0 26px; font-size:14px; }}
h2 {{ font-size:19px; margin:38px 0 6px; letter-spacing:-.01em; }}
h2 .n {{ color:var(--mut); font-weight:400; font-size:15px; }}
.lead {{ color:var(--mut); margin:0 0 16px; max-width:80ch; }}
code {{ background:#0b0f14; border:1px solid var(--bd); border-radius:4px; padding:.5px 4px;
  font:12.5px/1.4 "SF Mono",ui-monospace,Menlo,monospace; color:#c9d4e3; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:18px 0 8px; }}
.card {{ background:var(--panel); border:1px solid var(--bd); border-radius:10px; padding:14px 16px; }}
.card .big {{ font-size:30px; font-weight:700; letter-spacing:-.02em; }}
.card .lbl {{ color:var(--mut); font-size:12.5px; margin-top:2px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 10px; }}
.chip {{ cursor:pointer; border:1px solid var(--bd); background:var(--panel); color:var(--tx);
  border-radius:999px; padding:5px 12px; font-size:13px; transition:.12s; }}
.chip b {{ font-size:14px; }}
.chip:hover {{ border-color:var(--acc); }}
.chip.active {{ background:var(--acc); color:#04101f; border-color:var(--acc); }}
.chip.reset {{ opacity:.8; }}
.chip.unenforced b {{ color:var(--unenforced); }} .chip.unenforced.active b {{ color:#04101f; }}
.chip.protocol b {{ color:var(--protocol); }} .chip.protocol.active b {{ color:#04101f; }}
.chip.ledger b {{ color:var(--ledger); }}
.chip.test b {{ color:var(--test); }} .chip.test.active b {{ color:#04101f; }}
.chip.invariant b {{ color:var(--invariant); }}
table {{ width:100%; border-collapse:collapse; margin-top:6px; font-size:13.5px; }}
th {{ text-align:left; color:var(--mut); font-weight:600; font-size:12px; text-transform:uppercase;
  letter-spacing:.04em; padding:8px 10px; border-bottom:1px solid var(--bd); position:sticky; top:0;
  background:var(--bg); }}
td {{ padding:10px; border-bottom:1px solid var(--bd); vertical-align:top; }}
tr:hover td {{ background:var(--panel); }}
.lid,.sid {{ font-weight:700; color:var(--acc); white-space:nowrap; }}
.ldate,.sname {{ white-space:nowrap; color:var(--mut); }}
.ltext {{ max-width:640px; }} .lsrc {{ color:var(--mut); font-size:12px; max-width:220px; }}
.sgate {{ color:var(--mut); }}
.pill {{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:11.5px; font-weight:600;
  white-space:nowrap; }}
.p-unenforced {{ background:rgba(240,136,62,.16); color:var(--unenforced); border:1px solid rgba(240,136,62,.4); }}
.p-protocol {{ background:rgba(163,113,247,.16); color:var(--protocol); border:1px solid rgba(163,113,247,.4); }}
.p-ledger {{ background:rgba(139,148,158,.16); color:var(--ledger); border:1px solid rgba(139,148,158,.4); }}
.p-test {{ background:rgba(63,185,80,.16); color:var(--test); border:1px solid rgba(63,185,80,.4); }}
.p-invariant {{ background:rgba(35,134,54,.2); color:#4ac26b; border:1px solid rgba(35,134,54,.5); }}
.s-dead {{ background:rgba(110,118,129,.16); color:#adbac7; border:1px solid var(--bd); }}
.s-collecting {{ background:rgba(88,166,255,.16); color:var(--collecting); border:1px solid rgba(88,166,255,.4); }}
.s-gated {{ background:rgba(210,153,34,.16); color:var(--gated); border:1px solid rgba(210,153,34,.4); }}
.s-built {{ background:rgba(35,134,54,.2); color:#4ac26b; border:1px solid rgba(35,134,54,.5); }}
.s-blocked {{ background:rgba(72,79,88,.3); color:var(--mut); border:1px solid var(--bd); }}
.s-idea {{ background:rgba(139,148,158,.12); color:var(--mut); border:1px solid var(--bd); }}
.panel {{ background:var(--panel); border:1px solid var(--bd); border-radius:12px; padding:20px 22px; margin-top:8px; }}
.grad {{ display:flex; align-items:stretch; gap:0; margin:14px 0; flex-wrap:wrap; }}
.step {{ flex:1; min-width:150px; background:var(--panel2); border:1px solid var(--bd); padding:12px 14px;
  position:relative; }}
.step:first-child {{ border-radius:8px 0 0 8px; }} .step:last-child {{ border-radius:0 8px 8px 0; }}
.step h4 {{ margin:0 0 4px; font-size:13.5px; }} .step p {{ margin:0; color:var(--mut); font-size:12px; }}
.step .dot {{ width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:6px; }}
.flow {{ display:grid; gap:10px; margin-top:6px; }}
.flow .row {{ display:grid; grid-template-columns:190px 1fr; gap:14px; padding:11px 0; border-bottom:1px solid var(--bd); }}
.flow .row:last-child {{ border-bottom:none; }}
.flow .who {{ font-weight:600; }} .flow .who small {{ display:block; color:var(--mut); font-weight:400; font-size:11.5px; margin-top:2px;}}
.flow .what {{ color:var(--tx); font-size:13.5px; }} .flow .what .m {{ color:var(--mut); }}
ul.log {{ margin:6px 0 0; padding-left:18px; columns:1; }}
ul.log li {{ margin:3px 0; font-size:12.5px; color:var(--mut); }}
.foot {{ color:var(--mut); font-size:12px; margin-top:40px; border-top:1px solid var(--bd); padding-top:14px; }}
.hidden {{ display:none; }}
a {{ color:var(--acc); }}
</style></head>
<body><div class="wrap">
<h1>kalshi.headless — problem ledger since inception</h1>
<p class="sub">Every recorded problem — bugs, methodology traps, venue gotchas, and disproved strategies — parsed live from the repo's append-only registries. Generated {now} · source of truth: <code>kb/lessons/00-lessons.md</code>, <code>kb/strategies/00-index.md</code>, <code>kb/00-LOG.md</code>.</p>

<div class="cards">
  <div class="card"><div class="big">{len(lessons)}</div><div class="lbl">codified lessons (L1–L{max(int(r['id'][1:]) for r in lessons)})</div></div>
  <div class="card"><div class="big" style="color:var(--unenforced)">{lb.get('unenforced',0)}</div><div class="lbl">still UNENFORCED (open work queue)</div></div>
  <div class="card"><div class="big" style="color:#4ac26b">{lb.get('invariant',0)+lb.get('test',0)}</div><div class="lbl">hardened into a CI assert / test</div></div>
  <div class="card"><div class="big" style="color:#adbac7">{sb.get('dead',0)}</div><div class="lbl">strategies proven dead</div></div>
  <div class="card"><div class="big">{len(log_heads)}</div><div class="lbl">run-log entries read by the loops</div></div>
</div>

<h2>1 · Lessons ledger <span class="n">— the codified-problem catalog</span></h2>
<p class="lead">CLAUDE.md's rule is <em>invariants over memory</em>: every hard-won problem becomes a row the moment it's learned, then climbs an enforcement gradient. <strong>UNENFORCED</strong> rows are the standing work queue; <strong>ledger-only</strong> is an honest terminal state (venue behavior / methodology judgment that can't be asserted). Click a status to filter.</p>

<div class="grad">
  <div class="step"><h4><span class="dot" style="background:var(--unenforced)"></span>UNENFORCED</h4><p>learned the hard way; nothing stops the next variant yet</p></div>
  <div class="step"><h4><span class="dot" style="background:var(--protocol)"></span>protocol</h4><p>encoded in a charter / probe precedent</p></div>
  <div class="step"><h4><span class="dot" style="background:var(--test)"></span>test</h4><p>a regression test pins the exact fix</p></div>
  <div class="step"><h4><span class="dot" style="background:var(--invariant)"></span>invariant</h4><p>a CI assert fails the build on recurrence</p></div>
</div>

<div class="chips">
  <button class="chip reset active" data-filter="all">All {len(lessons)}</button>
  {lesson_chips}
</div>
<div style="overflow-x:auto">
<table id="lessons">
<thead><tr><th>ID</th><th>Date</th><th>Lesson</th><th>Enforcement</th><th>Source</th></tr></thead>
<tbody>
{lesson_rows_html()}
</tbody></table>
</div>

<h2>2 · Strategy registry <span class="n">— hypotheses the codebase investigated and closed</span></h2>
<p class="lead">A distinct class of "problem": each S-candidate is a falsifiable money-making hypothesis. The prime directive lets one graduate only on a bootstrapped CI <strong>&gt; 0 at real fillable asks</strong>. Most die there — a dead strategy recorded honestly is a success, not a failure. {sb.get('dead',0)} dead, {sb.get('collecting',0)} still collecting, 0 live.</p>
<div class="chips">{strat_chips}</div>
<div style="overflow-x:auto">
<table id="strats">
<thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Binding gate / verdict</th></tr></thead>
<tbody>
{strat_rows_html()}
</tbody></table>
</div>

<h2>3 · How recent logs are read &amp; acted on</h2>
<p class="lead">The findings and lessons above aren't passive notes — an autonomous cloud loop system reads them every few hours and moves problems up the enforcement gradient. This is the read→act machinery.</p>

<div class="panel">
<div class="flow">
  <div class="row"><div class="who">kalshi-collector <small>hourly · Haiku</small></div><div class="what">Runs <code>python -m collection.hourly_pass</code> — appends L2 tape. Nothing else, ever. <span class="m">Push to <code>main</code> fails intermittently → strands tape on <code>tape/hourly-*</code> branches (L17).</span></div></div>
  <div class="row"><div class="who">kalshi-research-loop <small>every 3h · Sonnet 5</small></div><div class="what">The <strong>doer</strong>. Steps 0a→9 of <code>LOOP-QUEUE.md</code>: history-integrity check → claim-check open PRs → <strong>step 0b stranded-tape sweep</strong> → execute ONE queue milestone → gates (<code>pytest</code> + <code>invariants.py --full</code>) → append to <code>kb/00-LOG.md</code> → PR + self-merge. <span class="m">Idle-run policy: "sweep only" is invalid — an idle run must convert an UNENFORCED lesson into an invariant, prep a gated probe, or run a data-quality deep-dive.</span></div></div>
  <div class="row"><div class="who">kalshi-edge-hunter <small>nightly 04:15Z · Opus 4.8</small></div><div class="what">The <strong>thinking seat</strong>. Reads the last 24h of <code>kb/00-LOG.md</code> + new <code>findings/</code>, then: (1) <strong>adversarially re-checks</strong> one load-bearing number per finding — a failure opens a GitHub issue + Priority:high phone note; (2) replenishes the queue (Q21 idea-gen) if &lt;2 eligible items; (3) pre-builds scripts for probes whose data-gate opens within 72h. Ends with a plain-English ntfy brief.</div></div>
  <div class="row"><div class="who">kb-distiller <small>agent · on demand</small></div><div class="what">The <strong>compounder</strong>. Turns verified findings + worker lesson-candidates into new ledger rows, and escalates UNENFORCED rows into invariants/tests. This is the mechanism that empties the orange column above.</div></div>
  <div class="row"><div class="who">kalshi-weekly-retro <small>Sun 12:00Z · Opus 4.8</small></div><div class="what">Diffs live routines vs <code>ops/ROUTINES.md</code>, flags stuck PRs &gt;5d, verifies the daily briefs actually flowed (a silent day is Priority:high), reports stranded-branch trend.</div></div>
  <div class="row"><div class="who">ntfy-watch <small>hourly</small></div><div class="what">Relays every leg's phone note to Ryan's device over a secret ntfy topic — the human-in-the-loop channel for anything needing a decision.</div></div>
</div>
</div>
<p class="lead" style="margin-top:16px"><strong>Two guardrails on acting.</strong> (a) The <strong>two-agent verdict rule</strong>: no registry flip / bootstrap CI / kill decision commits without an independent <code>verifier</code> agent re-run confirming it — unconfirmed verdicts are PROVISIONAL and flip nothing. (b) <strong>Structural stop</strong>: a cloud run can never place a trade — the gate is missing credentials (paper tier only), not behavior. <span style="color:var(--mut)">Two operational scars are baked into step 0: cloud sessions <em>cannot</em> <code>git push origin main</code> (L4, permission boundary) and <code>main</code> was silently rewound to a 6-day-old checkpoint on 2026-07-08 (step 0a integrity check exists because of it).</span></p>

<h3 style="margin:26px 0 4px;font-size:15px">Most recent run-log entries (newest first)</h3>
<ul class="log">
{recent_log}
</ul>

<p class="foot">Self-contained · no external requests · regenerate with <code>python scripts/gen_problems_dashboard.py</code>. Problem definitions are exactly the repo's own: a lesson is a row in the ledger; a dead strategy is a falsified hypothesis; an operational incident is whichever lesson/log entry recorded it. Nothing here is hand-authored — all rows are parsed from the append-only registries.</p>

<script>
const chips = document.querySelectorAll('.chip');
const rows = document.querySelectorAll('#lessons tbody tr');
chips.forEach(c => c.addEventListener('click', () => {{
  chips.forEach(x => x.classList.remove('active'));
  c.classList.add('active');
  const f = c.dataset.filter;
  rows.forEach(r => r.classList.toggle('hidden', f !== 'all' && r.dataset.bucket !== f));
}}));
</script>
</div></body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(HTML)
print(f"wrote {OUT}  ({len(HTML):,} bytes)")
print(f"lessons={len(lessons)} buckets={lb}")
print(f"strategies={len(strategies)} buckets={sb}")
print(f"log_entries={len(log_heads)}")
