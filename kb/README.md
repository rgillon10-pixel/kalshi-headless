# Knowledge Base — charter & protocol

This KB exists to **generate a profitable set of strategies on Kalshi**. It is
not an encyclopedia. Every entry must eventually connect to a testable edge.

## The method (Karpathy-style)

We build this KB the way Karpathy learns and teaches. Five rules:

1. **First principles, not memorization.** Derive each concept from the ground
   up. Don't write "Kalshi charges a fee"; write the fee *formula*, show where it
   bites, and link the source. If we can't derive it, we don't claim it.

2. **"What I cannot create, I do not understand."** Every non-trivial claim gets
   a minimal, runnable reproduction in `../scripts/`. A pricing rule → a 20-line
   script that prices a real market. A study's result → a script that reproduces
   its core statistic on toy or real data. Theory without code is a TODO, not
   knowledge.

3. **Smallest thing that captures the essence (nanoGPT ethos).** Prefer the
   minimal example that makes the idea click over the exhaustive treatment. One
   clean worked example beats ten paragraphs.

4. **Append-only running log.** `00-LOG.md` is a timestamped journal of what we
   learned, what we tried, and what *failed*. Never delete from it — dead ends are
   data. Entries link out to the notes/scripts they spawned.

5. **Legible to a cold reader.** Write so a future session (or another agent)
   can pick up with zero context. State confidence explicitly. Default trust =
   FALSE (see `../CLAUDE.md`): mark every claim `proven` / `cited` / `speculative`.

## How it grows

The KB is alive. The loop:

```
observe (codebase / market / paper)
  → log it in 00-LOG.md
  → distill into a note under the right folder
  → if it's a claim, write a script that proves it
  → if it suggests an edge, open a candidate in strategies/
  → revisit & revise notes as understanding deepens (note the revision in the log)
```

Notes are versioned by editing in place; the *history of understanding* lives in
the log and in git. When a note is superseded, leave a one-line "superseded by …"
pointer rather than silently rewriting history.

## Layout

- `00-LOG.md` — append-only running log. **Start here to see the journey.**
- `glossary.md` — precise definitions of every term we use.
- `kalshi-api/` — how Kalshi actually works: API, auth, market structure, fees,
  rate limits, data. The substrate every strategy runs on.
- `quant-finance/` — distilled peer-reviewed literature, each note tied to what
  it implies for a Kalshi edge.
- `strategies/` — candidate strategies. Each is a falsifiable hypothesis with a
  binding test, not a vibe.
- `lessons/` — the compounding ledger (added 2026-07-06): every hard-won lesson
  as a row with provenance and an enforcement status (`UNENFORCED` → `protocol`
  → `test` → `invariant`). Owned by the `kb-distiller` agent; UNENFORCED rows
  are its standing work queue.
- `_sources/` — raw captured sources (paper abstracts, API doc snapshots) so
  claims stay auditable even if the web changes.

## Maturity tags (put one at the top of every note)

`stub` → `drafted` → `cited` → `reproduced` → `battle-tested`

A note may only claim `reproduced` if there is a script in `../scripts/` that a
cold run reproduces. `battle-tested` requires real-ask evidence.
