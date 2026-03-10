# Project Agent Instructions

This file is the authoritative guide for AI coding agents (like OpenAI Codex) operating on this repository. It provides project conventions, documentation structure, build/test commands, and expectations for how agents should behave.

---

## 📁 Project Documentation Conventions

This project stores documentation under `docs/` with a fixed and stable structure:

- `docs/overview.md` → Project overview and goals.
- `docs/architecture.md` → Current software architecture description.
- `docs/api.md` → API specifications and agreements.
- `docs/coding-guidelines.md` → Code style and conventions.
- `docs/testing.md` → Testing strategies, types, and workflows.
- `docs/references.md` (optional) → Background materials, external references, and design rationale.
- `docs/CHANGELOG.md` → Summary of changes to `docs/` and architecture over time.

**Agents should never inline the entire docs content in `AGENTS.md`.**
`AGENTS.md` is an index and *operational guide* - not a replacement for individual docs.
When detailed context is needed, agents must read the relevant file in `docs/`, not duplicate it here.
