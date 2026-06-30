# Designing a Memory & Context System for Claude Code — Design Brief

> **Date:** 2026-06-30
> **Audience:** a fresh Claude Code session tasked with designing/improving a
> long-term memory + context system for the project owner.
> **Status:** input artifact. Read in full, then propose or refine an
> architecture and a concrete build plan (§7–§8).

---

## 0. How to use this document

This is a briefing, not a spec. The owner already runs a Karpathy-style markdown
knowledge base (described in §1). The goal is **not** to start over but to extend
that KB into a complete system that covers *both* context axes (§3), because the
existing KB only solves one of them.

When you (the receiving session) act on this:
1. Confirm the owner's current setup matches §1; correct it if not.
2. Treat §4 as the menu of techniques and §7 as the recommended composition.
3. Drive toward the decisions and build steps in §8 — that's the deliverable.
4. Don't add infrastructure (vector DBs, graph memory) without justifying it
   against the benchmark note in §4 (simple filesystem memory is competitive).

---

## 1. The owner's situation (ground truth for design)

- **Workloads:** (a) long-lived programming projects spanning many sessions, and
  (b) a research literature knowledge base for ESIBD (electrospray ion-beam
  deposition) — PDFs extracted, summarized, and filed as atomic notes.
- **Runtime:** Claude Code with Opus, often run **autonomously** on a local
  machine. Self-hosted / local-first / privacy-preserving is a hard preference.
- **Existing KB (the thing to extend):** a three-layer Karpathy-style wiki —
  - `raw/` — immutable, human-curated source material (read-only).
  - `wiki/` — the markdown KB the agent maintains: `index.md` router,
    `architecture.md`, `patterns.md`, `gotchas.md` (status-tagged), append-only
    `log.md`, `concepts/`, `decisions/` (numbered ADRs, immutable once Accepted),
    `sources/`.
  - `CLAUDE.md` — a thin router that points at the wiki + skills, holds almost
    no knowledge itself.
  - Skills: `wiki-ingest`, `wiki-query`, `wiki-lint` — each ends by writing
    knowledge back (update gotchas/decisions, refresh index, append to log).
- **Constraint that shapes everything:** the owner wants the system to *compound*
  across sessions without manual babysitting, and to survive autonomous runs.

---

## 2. Core mental model

Treat the context window as an **OS memory hierarchy**:

- context window ≈ RAM / L1 cache — small, fast, expensive, volatile.
- durable store (files, the KB, a memory backend) ≈ disk — large, slow, persistent.
- the agent's job is to **page in** only the high-signal tokens a task needs,
  just-in-time, and page out / never-load the rest.

The discipline is **curation, not accumulation**. The reason this matters even
with a large-window model is **context rot**: as the window fills, recall
degrades — every token attends to every other token (n² attention), so a window
stuffed with marginally-relevant content measurably *lowers* output quality. A
big context window is a budget to spend carefully, not a bucket to fill.

This same metaphor is now showing up formally in the literature (demand-paging
for context windows; managing context like git commits/branches). The takeaway:
the window is working memory; everything durable lives outside it and is fetched
on demand.

---

## 3. Two distinct axes — do not conflate them

The single most important framing. The owner's pain ("context runs out over
multiple sessions") actually spans two separate problems:

**Axis A — intra-session context management.** Keeping a *single* long-running
session coherent before it exhausts its window mid-task. Solved by compaction,
tool-result clearing, sub-agent isolation, programmatic tool calling, and the
Research→Plan→Implement workflow.

**Axis B — cross-session / long-term memory.** Carrying knowledge *between*
sessions so each one compounds instead of restarting. Solved by structured
note-taking / agentic memory — which is exactly what the existing KB is.

**The KB only addresses Axis B.** It does nothing for a single session blowing
its window. A complete system needs both axes, and they are complementary, not
substitutes. Design for both explicitly.

---

## 4. The toolkit of levers (what the industry converged on)

There is no single blessed method — there is a vocabulary ("context
engineering") and a set of composable levers. Compose them; don't pick one.

| Lever | What it does | Axis | Cost / risk |
|---|---|---|---|
| **Compaction** | Summarize the transcript near the limit, reinitialize with the summary. Claude Code auto-compacts; `/compact` triggers it manually. | A | Aggressive compaction silently drops subtle context whose importance surfaces later. |
| **Tool-result clearing** | Lightest-touch compaction: drop old tool calls/results from the window once consumed. A platform feature on the Claude Developer Platform. | A | Nearly free; safe. (Research finding: simple "observation masking" of stale tool output beat LLM summarization on coding tasks — prefer it before heavier compaction.) |
| **Agentic memory / structured note-taking** | Agent writes notes to durable storage outside the window, reads them back after a reset/new session. **This is the KB.** | B | Read-only drift: if notes are never re-read or never updated, the store rots. |
| **Sub-agent isolation** | Orchestrator spawns focused sub-agents, each with a clean window; only summaries return to the main thread. | A | Token blow-up — multi-agent can use ~15× the tokens of a single chat. Use for genuinely separable big sub-tasks only. |
| **Progressive disclosure / Skills** | Load instructions/docs/scripts on demand only when relevant, instead of stuffing the system prompt / `CLAUDE.md`. The KB already uses this. | A+B | Non-determinism: the model must *choose* to load the skill; it sometimes won't. |
| **Programmatic tool calling** | Orchestrate tools in code so intermediate outputs are consumed by the code and only the final result enters the window. | A | Keeps large tool outputs out of context entirely; needs a code-exec path. |
| **Research → Plan → Implement** | Split the work; the plan becomes a durable artifact that survives context resets. Workflow-layer version of the same idea. | A+B | Discipline cost; the plan must be persisted (see §7) or `/compact` eats it. |

**Storage-backend note (important for the owner's local-first leaning):** you do
**not** need a vector or graph database for this. A benchmark (Letta, LoCoMo)
found agents using *simple filesystem storage* hit ~74% vs ~68.5% for a
graph-based approach — the conclusion was that memory quality is mostly about
*how the agent manages context*, not the retrieval mechanism. Markdown-on-disk
(what the KB already is) is competitive and local-first. Add fancier retrieval
only when §6's scaling concern actually bites.

---

## 5. Assessment of the existing Karpathy KB

### What it gets right (keep these)

- **Thin router / `CLAUDE.md`.** The always-loaded context stays small; knowledge
  is pulled on demand. This is correct progressive-disclosure design.
- **Three mutation policies preserve provenance.** Immutable ADRs (supersede,
  don't edit) + living docs + append-only log. Plain summary-memory destroys the
  *why a decision changed*; the ADR rule keeps it. This is a real advantage over
  default compaction-style memory and is the KB's strongest feature.
- **Skills that force write-back.** This attacks the #1 failure mode of any
  memory system — read-only drift. Right instinct.
- **Status-tagged gotchas** (ANTICIPATED / RESOLVED / OPEN) are effectively a
  human-legible regression memory. High ROI; a recorded fix never gets
  re-debugged from scratch.

### Where it falls short (design against these)

- **It only covers Axis B.** No story for in-session window exhaustion.
- **It does not self-enforce** (the owner's own doc admits this). Unmaintained,
  it rots into authoritative-looking stale docs — *worse* than nothing.
- **Retrieval is router + one-hop wikilinks.** Human-legible, but won't scale.
- **Single-writer assumption.** Concurrent sub-agents writing to living pages
  (`architecture.md`, `gotchas.md`) have no merge story.

---

## 6. Key risks to design against

1. **Rot with no health signal.** During autonomous ingests, does the agent
   actually maintain status tags and supersede ADRs correctly, or drift? There is
   currently **no eval and no measurement**. The industry's hardest-learned
   lesson: context engineering "by vibes" ships silent regressions. Measure it.
2. **Retrieval doesn't scale.** Router-plus-one-hop-links works at hundreds of
   pages. For an ESIBD literature KB heading into thousands of notes, it will
   either over-read (blow context) or miss pages that have no direct inbound
   link. A second retrieval path (search) is needed past some threshold.
3. **The in-session gap.** Long autonomous coding runs will exhaust the window
   regardless of how good the KB is. Without compaction discipline + a persisted
   plan, the run degrades or loses its task thread.
4. **Concurrency / write-amplification.** Parallel sub-agents writing back, and
   ingests that touch 10–15 files each, create churn and merge conflicts on a
   fast-moving codebase. Needs a write/merge convention.
5. **Cost.** For short projects the KB overhead loses to a flat file (owner's own
   §0). Don't apply the full machinery to small/short work.

---

## 7. Recommended target architecture

A layered system, not a single mechanism. Each layer maps to a lever in §4.

**Layer 1 — Long-term memory tier (Axis B): the KB, kept.**
Keep the existing Karpathy KB as-is for cross-session knowledge. It already does
provenance better than default memory. The improvements below wrap around it.

**Layer 2 — In-session hygiene (Axis A): add this — it's the current gap.**
- Adopt **Research → Plan → Implement**. Write the plan to a durable file (e.g.
  `raw/plans/<task>.md` or a scratch note) **before** implementing, so `/compact`
  or a session reset can't destroy it — the next session re-reads the plan.
- Lean on **auto-compaction + tool-result clearing**; prefer clearing/masking
  stale tool output before heavy summarization.
- Spin **focused sub-agents** for large, separable sub-tasks so the main thread
  stays clean — but budget for the ~15× token cost and reserve it for genuinely
  parallel work.

**Layer 3 — Retrieval (both axes): two paths, not one.**
- Keep **router + wikilinks** as the legible, structured path.
- Add a **grep / full-text (and optionally local semantic) search** path over
  `wiki/` for when link-following misses or the KB grows large. grep first,
  links second. Defer any vector/graph store until §6.2 actually bites.

**Layer 4 — Governance (the thing that stops rot).**
- Run `wiki-lint` on a **schedule**, not only on request (orphan pages, broken
  links, stale claims, missing concept pages, contradictions).
- Add a **tiny eval harness**: a fixed set of "given question X, the right pages
  are {A,B,C}" cases, run after ingests, so retrieval regressions are caught.
  Even a handful of cases turns "vibes" into a signal. This is the single most
  important addition the owner is missing.
- Define a **write/merge convention** for concurrent agents (e.g. sub-agents
  *report findings*; only the main session writes back to living pages; the
  append-only `log.md` reconstructs ordering).

---

## 8. Open questions for the receiving session to resolve

Drive the design conversation to concrete answers on:

1. **Routing rule — what lives where?** Precise boundaries between `raw/`
   (immutable sources + plans), `wiki/` (curated knowledge), and any
   session-scratch memory. Where does an autonomous run write progress notes?
2. **Compaction policy.** When to clear tool results vs full-compact vs start a
   fresh thread. What must *never* be compacted away (the active plan, open
   gotchas)?
3. **Sub-agent contract.** Do sub-agents write to the KB or only report back? If
   they write, what's the merge/lock convention? Token budget per sub-agent?
4. **Retrieval threshold.** At what KB size do you switch on the search path?
   grep-only, or add local embeddings (and which local model, given local-first)?
5. **Eval design.** What does a "KB health pass" check, how many cases, and what
   triggers it (every ingest? nightly? pre-merge)?
6. **Skill triggering reliability.** How to make the agent reliably load
   `wiki-query`/`wiki-ingest` (description tuning, explicit session protocol in
   `CLAUDE.md`) given that skill-loading is non-deterministic.
7. **ESIBD-KB vs code-KB.** One KB or two? The literature KB and a coding-project
   KB have different growth and retrieval profiles — decide whether they share
   infrastructure or stay separate vaults.

---

## 9. Key references (fetch if useful)

- Anthropic — *Effective context engineering for AI agents*:
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic Claude Cookbook — *compaction, tool-result clearing, memory*:
  https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools
- LangChain — *Context Engineering for Agents* (sub-agent isolation, the ~15×
  token figure): https://www.langchain.com/blog/context-engineering-for-agents
- Latitude — *Context Engineering for Coding Agents* (Dex/HumanLayer
  Research→Plan→Implement): https://latitude.so/blog/context-engineering-guide-coding-agents
- Martin Fowler — *Context Engineering for Coding Agents* (Skills / progressive
  disclosure): https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html
- *The Missing Memory Hierarchy: Demand Paging for LLM Context Windows*:
  https://arxiv.org/abs/2603.09023
- *Git Context Controller: Manage the Context of LLM-based Agents like Git*:
  https://arxiv.org/abs/2508.00031
- Letta LoCoMo benchmark (filesystem memory vs graph) — summarized at:
  https://www.pixelmojo.io/blogs/context-engineering-ai-coding-agents-beyond-claude-md

> Benchmark figures (74% vs 68.5%, ~15× tokens, ~80% SWE-bench for the Opus
> generation) are reported values from the sources above; verify against the
> primary source before relying on them.
