# Agent Instructions

- Do not use `codex/` as a branch name prefix in this repository. Use semantic branch prefixes such as `feat/`, `fix/`, `chore/`, or `docs/`; for example, `feat/pr-748-dev`.
- Before modifying frontend code, read `frontend/SPEC.md`.
- When the user describes a requirement, propose an implementation plan before changing code, and wait for the user to be satisfied before making edits.
- After creating or switching to a new branch, run `git pull` before development. Branch names must use semantic prefixes and reflect the requirement content.
- When committing, include only changes related to the current feature or fix.
- Before committing, fetch the latest remote code, rebase the branch onto it, then run pre-commit and unit tests.
- When execution hits a pitfall such as insufficient permissions or missing dependencies, ask the user whether to document that pitfall.
