# Plans

Design documents, the record of initial changes, and what's coming next.

The `docs/superpowers/specs/` directory (referenced from `CONTRIBUTING.md`)
is the canonical design spec. This folder is the higher-level narrative —
why we forked, what we changed in the first cut, and what's still open.

## Contents

- [`00-vision.md`](00-vision.md) — what this fork is for and what it
  deliberately is not.
- [`01-initial-changes.md`](01-initial-changes.md) — what shipped in
  v0.1.0-alpha, broken down by the eight implementation phases.
- [`02-roadmap.md`](02-roadmap.md) — known-missing items deferred past v1,
  and the rough order we'd tackle them in.

## How to propose a change

Open an issue or a PR. For anything that touches the UI shell, the player
adapter, or the protocol-compatibility boundary, sketch the change in this
folder first (or in `docs/superpowers/specs/`) before writing code. The
goal is to keep the rebase-with-upstream cadence cheap, which means
preserving the boundary between `syncplay/ui/modern/` (ours) and the
upstream-compatible core (`client.py`, `protocols.py`, `constants.py`,
`ConfigurationGetter.py`).
