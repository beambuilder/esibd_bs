# LLM Knowledge-Base Infrastructure — Starter

> A portable bootstrap for running a Karpathy-style project wiki that Claude Code
> sessions read from and write to. Drop this into a new repo as the seed for
> `CLAUDE.md` + a `wiki/` knowledge base. Project-agnostic.
>
> **Core idea:** a flat `CLAUDE.md` loses the *why* behind changes, has no
> resolution status for traps, and no cross-session history. This structure fixes
> that with **three different mutation policies** — immutable decisions, living
> docs, append-only log — plus **skills that force knowledge to be written back**
> so each session compounds instead of restarting.

---

## 0. When to use this (and when not)

Use it when the project is **long-lived, spans many sessions/subagents, and has
non-obvious domain knowledge** (gotchas, hard-won decisions, traps that are
expensive to re-discover). That is the regime where it beats a flat file.

**Do not bother** for a small or short project: the per-session cost of reading
the index and following links outweighs the benefit. A flat `CLAUDE.md` is
cheaper and just as good below ~a few hundred lines of project knowledge.

The structure does **not** self-enforce. It pays off only if the write-back
discipline (§4, §5) is actually followed. Unmaintained, it rots into stale docs
that are *worse* than nothing because they look authoritative.

---

## 1. Three-layer structure

```
raw/        immutable source material (specs, papers, transcripts, plans).
            Read-only. The HUMAN curates this layer. Never edit in place.
wiki/       the markdown knowledge base. Claude maintains this via the skills.
CLAUDE.md   a lean ROUTER. Points at the wiki + the skills. Holds almost no
            knowledge itself — knowledge lives in wiki/.
```

Keeping `CLAUDE.md` thin is deliberate: it is loaded into *every* session's
context. It should route, not store. Storage lives in `wiki/`, pulled on demand.

---

## 2. Page taxonomy (`wiki/`)

Each page type has **one job** and **one mutation policy**. This separation is
the whole trick.

| Page / dir            | Job                                              | Mutation policy |
|-----------------------|--------------------------------------------------|-----------------|
| `index.md`            | Router. Every page reachable from here, each with a one-line summary. | Living — keep current. |
| `architecture.md`     | The system end-to-end, as currently designed.    | Living — overwrite as design changes. |
| `patterns.md`         | Recurring idioms/conventions that recur.         | Living — append/revise. |
| `gotchas.md`          | Traps, footguns, open risks. **Highest ROI page.** | Living, but entries carry **status** (see §3). |
| `log.md`              | Chronological record of operations.              | **Append-only.** Never rewrite history. |
| `concepts/<x>.md`     | One domain concept each, explained once.         | Living. |
| `decisions/NNNN-*.md` | One ADR (Architecture Decision Record) each.     | **Immutable once Accepted** (see §3). |
| `sources/<x>.md`      | One summary page per ingested `raw/` source.     | Written once at ingest, lightly revised. |

Naming: `concepts/` and `sources/` use kebab-case slugs; `decisions/` use a
zero-padded number + slug (`0007-local-only-storage.md`). Keep an ADR template at
`decisions/0000-template.md`.

---

## 3. The invariants that make it work

These are non-negotiable; they are what a flat file cannot give you.

1. **`index.md` is the single router.** Every page is reachable from it with a
   one-line summary. A session reads *this first* to know what exists and where —
   cheap recall. Update it whenever you add/rename a page.

2. **ADRs are immutable once Accepted.** Do not edit an accepted decision.
   **Supersede** it with a new ADR and mark the old one
   `*superseded by NNNN.*`. This preserves *why the mind changed* — the single
   thing a flat `CLAUDE.md` loses hardest, because in-place edits erase history.

3. **`log.md` is append-only**, newest at the bottom, each entry prefixed
   `## [YYYY-MM-DD] <op> | <title>` so it stays greppable. `<op>` ∈
   {`ingest`, `query`, `lint`, `build`, …}. This is the cross-session "what
   happened when" that git blame approximates badly.

4. **Gotchas carry status, not just description.** Tag each:
   `ANTICIPATED` (risk, no code yet), `RESOLVED (<milestone>)` (with the fix and
   the residual risk), or `OPEN`. A trap whose fix is recorded never gets
   re-debugged from scratch. This is the page that saves the most session time.

5. **Link liberally with `[[wikilinks]]`** (page name, no path, no extension).
   Every gotcha/pattern/concept links to the decision or source that explains it.
   The graph is what lets a query fan out one hop and find context.

6. **Convert relative dates to absolute** in anything persisted ("today",
   "next week" are meaningless to a future session).

---

## 4. Operations as skills (the compounding engine)

Knowledge bases that are only *read* go stale. The engine that makes this one
*compound* is a small set of skills whose procedures **force a write-back** at
the end. Put these in `.claude/skills/<name>/SKILL.md`. Three are enough:

**`wiki-ingest`** — when the human drops a source in `raw/` and asks to file it.
1. Read the full source. 2. Surface 3–7 key takeaways for the human to react to.
3. Write `sources/<slug>.md`. 4. Update affected `architecture`/`concepts`/
`patterns`/`gotchas`/`decisions`. 5. Refresh `index.md`. 6. Append to `log.md`.
*(One ingest typically touches 10–15 files — that fan-out is the point.)*

**`wiki-query`** — when the human asks a substantive question.
1. Read `index.md`. 2. Follow `[[wikilinks]]` into relevant pages (one hop
deeper if useful). 3. Answer with **inline citations to wiki paths**. 4. **If the
answer is a novel synthesis worth keeping, file it back** as a new page/section
(on confirmation). 5. Log the query. Step 4 is what makes future queries cheaper.

**`wiki-lint`** — when the human asks to audit/health-check.
1. Walk `wiki/`, build the inbound/outbound link map. 2. Find: stale claims
contradicted by newer sources, orphan pages (no inbound links), concepts
mentioned but lacking a page, broken links, contradictions, gaps worth a new
source/web search. 3. Present a categorized report — **do not silently edit**.
4. Apply fixes on approval. 5. Log it.

Skill `description:` fields should be written so the model auto-invokes them on
natural request ("ingest this", "what did we decide about X", "audit the wiki") —
no slash command needed.

---

## 5. Session protocol (put this in `CLAUDE.md`)

> - Treat `wiki/` as source of truth. **Before** a task: read `wiki/index.md` and
>   the relevant pages. **After** a task: update them.
> - Use `wiki-ingest` to file sources, `wiki-query` to answer from the wiki,
>   `wiki-lint` to audit. Don't hand-roll these.
> - ADRs in `wiki/decisions/` are immutable once Accepted — supersede, don't edit.
> - The human curates `raw/`; Claude maintains `wiki/`.
> - Log entries are prefixed `## [YYYY-MM-DD] <op> | <title>` so they stay
>   greppable.
> - Start here: read `wiki/index.md`.

---

## 6. Subagent / multi-session notes

- **Subagents start cold.** They do not inherit your context. Point them at
  `wiki/index.md` + named pages in the prompt so they bootstrap from the KB
  instead of re-deriving. The KB *is* the shared memory across agents.
- **Have subagents write findings back** to the wiki (or report them so the main
  session files them). A subagent that solves a trap and doesn't record it wasted
  the work — it dies and the knowledge dies with it.
- The append-only `log.md` is how parallel/sequential sessions reconstruct order
  of events without a chat history.

---

## 7. Anti-patterns (how it rots)

- **Storing knowledge in `CLAUDE.md`** instead of routing to `wiki/`. Bloats
  every session's context; defeats on-demand recall.
- **Editing accepted ADRs in place.** Destroys the decision history. Supersede.
- **Rewriting `log.md`.** It is a record, not a doc.
- **Gotchas without status.** "Here's a risk" with no RESOLVED/fix is just
  anxiety; the value is the recorded resolution.
- **Read-only usage.** If queries never file syntheses back and ingests never
  update gotchas, the KB stops compounding and becomes stale docs.
- **Orphan pages.** Anything not reachable from `index.md` is invisible — run
  `wiki-lint` to catch these.

---

## 8. Bootstrap checklist for a fresh repo

```
1. Create dirs:   raw/  wiki/  wiki/concepts/  wiki/decisions/  wiki/sources/
                  .claude/skills/{wiki-ingest,wiki-query,wiki-lint}/
2. Seed files:    wiki/index.md          (router stub)
                  wiki/architecture.md   (empty scaffold)
                  wiki/patterns.md  wiki/gotchas.md  wiki/log.md
                  wiki/decisions/0000-template.md
3. Write CLAUDE.md as a thin router (use §5 verbatim as the body).
4. Write the three SKILL.md files (use §4 procedures).
5. Drop your first spec/plan into raw/  →  ask Claude to "ingest it".
6. From then on: query / ingest / lint by natural request; the KB compounds.
```

---

## 9. One-paragraph version (paste into a new project to start)

> Set up a Karpathy-style project wiki. Three layers: `raw/` (immutable
> human-curated sources), `wiki/` (the markdown KB Claude maintains), and a thin
> `CLAUDE.md` that only routes to them. In `wiki/`: an `index.md` router (every
> page reachable, one-line summaries), `architecture.md`, `patterns.md`,
> `gotchas.md` (entries tagged ANTICIPATED/RESOLVED/OPEN with the fix),
> append-only `log.md` (`## [YYYY-MM-DD] <op> | <title>`), `concepts/` (one idea
> per page), `decisions/` (numbered ADRs, immutable once accepted — supersede,
> never edit), and `sources/` (one summary per ingested source). Link everything
> with `[[wikilinks]]`. Add three skills — `wiki-ingest`, `wiki-query`,
> `wiki-lint` — whose procedures always end by writing knowledge back (update
> gotchas/decisions, refresh index, append to log). Before any task read
> `index.md` + relevant pages; after, update them. The point is that each session
> compounds the last instead of restarting.
