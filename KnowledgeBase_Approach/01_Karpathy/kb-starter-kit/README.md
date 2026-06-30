# KB Starter Kit

Drop-in seed for a Karpathy-style project wiki that Claude Code reads from and
writes to. Copy the contents into a fresh repo and start ingesting.

See `KNOWLEDGE-BASE-STARTER.md` (one level up, or wherever you keep it) for the
full rationale. This folder is the **ready-to-copy scaffold**.

## What's here

```
CLAUDE.md                          thin router — knowledge lives in wiki/, not here
raw/                               immutable source material (human-curated)
wiki/
  index.md                         the router — every page reachable from here
  architecture.md                  system end-to-end (scaffold)
  patterns.md                      recurring idioms (scaffold)
  gotchas.md                       traps with status tags (scaffold)
  log.md                           append-only operations record
  concepts/                        one domain concept per page
  decisions/0000-template.md       ADR template (immutable once Accepted)
  sources/                         one summary per ingested source
.claude/skills/
  wiki-ingest/SKILL.md             file a new raw/ source into the wiki
  wiki-query/SKILL.md              answer from the wiki, file syntheses back
  wiki-lint/SKILL.md               audit the wiki for rot
```

## Use it

```
1. Copy this folder's contents into your new repo root.
2. Replace every <PROJECT> / <project> placeholder.
3. Drop your first spec/plan into raw/  →  tell Claude "ingest this".
4. From then on: ingest / query / lint by natural request. The KB compounds.
```

## The one rule that makes it work

Every operation **writes knowledge back**: ingest updates concepts/gotchas/
decisions + index + log; query files novel syntheses back; lint repairs rot.
Read-only usage = stale docs. The write-back is the whole point.
