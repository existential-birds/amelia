---
description: Analyze a doc, research its concepts, propose improvements with sources, and list OSS libraries. Use for Amelia architecture/ideas docs or design specs.
argument-hint: DOC=<path> [FOCUS="architecture,security,testing"] [DEPTH=quick|standard] [CONSTRAINTS="local-first,SQLite"]
---

You are running the Doc Research and Improvement workflow.

Inputs:
- Doc path: $DOC (required)
- Focus areas: $FOCUS (optional)
- Depth: $DEPTH (optional, quick|standard)
- Constraints: $CONSTRAINTS (optional)

If available, load and follow: `./.claude/skills/doc-research-improvements/SKILL.md`.
If the file is missing, follow this fallback:

1. Summarize the doc goals, scope, non-goals, and assumptions.
2. Extract concepts, frameworks, and techniques (classify by category).
3. Research each key concept with authoritative sources (cite links).
4. Propose ranked improvements with evidence, tradeoffs, and implementation notes.
5. Recommend OSS libraries/frameworks (license + fit).
6. Provide open questions.

Output format:
- Doc Snapshot
- Extracted Concepts (table)
- Evidence and Research Notes
- Improvements (Ranked)
- OSS and Framework Candidates (table)
- Open Questions
