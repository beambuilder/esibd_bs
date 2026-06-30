# <PROJECT> Wiki

A Karpathy-style LLM wiki: a curated knowledge base that this project's Claude
Code sessions read from and write to. This file is a lean **router** — the
knowledge itself lives in `wiki/`.

## Three-layer structure

- `raw/` — immutable source material (specs, papers, transcripts, plans).
  Read-only; the human curates this layer.
- `wiki/` — the markdown knowledge base. Maintained by the `wiki-*` skills.
- `CLAUDE.md` — this file: a lean router pointing at the wiki and the skills.

## Conventions

- Link between wiki pages with Obsidian-style `[[wikilinks]]` (page name, no
  path or extension).
- Log entries are prefixed `## [YYYY-MM-DD] <op> | <title>` so they stay
  greppable.
- ADRs in `wiki/decisions/` are immutable once **Accepted** — supersede with a
  new ADR rather than editing one in place.
- Convert relative dates ("today", "next week") to absolute before persisting.
- The human curates `raw/`; the skills maintain `wiki/`.

## Operations

Operations on the wiki live in `.claude/skills/`. The **wiki-ingest** skill
files new sources from `raw/` into `wiki/`. The **wiki-query** skill answers
questions from the wiki. The **wiki-lint** skill audits the wiki. Trigger each
by natural request — no slash command needed.

## Working rules

- Treat `wiki/` as source of truth. **Before** a task: read `wiki/index.md` and
  the relevant pages. **After** a task: update them.
- Use the `wiki-*` skills for all knowledge-base work: **wiki-ingest** to file
  sources, **wiki-query** to answer from the wiki, **wiki-lint** to audit.

## Start here

Read `wiki/index.md` — the wiki's table of contents.
