---
name: codex-sandbox-upload
description: Safely hand off the current local project to an AgentKit Studio cloud Codex Sandbox using a Studio URL and one-time project-upload authorization code. Use when the user asks to upload, migrate, continue, or open a local repository in Studio, especially when the prompt contains studio_url and authorization_code. Preserve tracked and non-ignored working-tree files, local edits and deletions, Git branch/commit/remote metadata, AGENTS.md, a generated HANDOFF.md, and GitHub CLI authentication needed to push changes; never copy Codex system prompts, conversations, SQLite state, global configuration, local skills, or SSH private keys.
---

# Codex Sandbox Upload

Transfer the project, not the local Codex runtime. Build a reviewable snapshot, create one persistent Studio Sandbox with the supplied one-time code, upload the snapshot, and restore it into the directory returned by Studio.

## Boundaries

Include only:

- Git tracked files and non-ignored untracked files, including working-tree edits and deletions
- repository-level `AGENTS.md` files selected by the same Git rules
- Git branch, HEAD commit, sanitized remote URL, and status metadata
- a generated `HANDOFF.md`; append the generated section when the project already has one

Never include:

- Codex system or developer prompts, conversations, rollout JSONL, or SQLite state
- `$CODEX_HOME`, local or global Skills, plugin caches, or global Codex settings
- SSH private keys, non-GitHub credentials, or global Git configuration
- ignored files such as `.env` unless they are deliberately tracked

Do not claim that the remote environment is an exact copy of local Codex. It is a project handoff into a separately configured Studio runtime.

## Workflow

1. Resolve the repository from the user's `repo` value or the current working directory. Confirm it with `pwd`.
2. Resolve `studio_url` and `authorization_code` from the user's prompt. Treat the authorization code as a secret: do not print it, write it to a file, or place it in the bundle.
3. For a GitHub remote, verify `gh auth token --hostname github.com` succeeds. GitHub authentication is transferred separately from the project bundle, installed with mode `0600`, and configured for HTTPS pushes. Never print the token. Convert an SSH-form GitHub remote to HTTPS instead of copying SSH keys.
4. Locate this Skill's `scripts/upload_current_dir.sh` and run a preview:

   ```bash
   scripts/upload_current_dir.sh --repo "$PWD" --dry-run
   ```

5. Review the preview's file count, size, GitHub authentication status, and sensitive-file warnings.
   - If high-risk filenames or possible secret assignments are present, stop and ask whether to exclude them locally or upload them with `--allow-sensitive`.
   - If no sensitive-file warnings are present and the current user request explicitly asks to upload, that request is sufficient confirmation.
6. Run the live handoff without echoing the authorization code or GitHub token:

   ```bash
   CODEX_PROJECT_UPLOAD_AUTHORIZATION_CODE="$authorization_code" \
     scripts/upload_current_dir.sh \
       --repo "$PWD" \
       --studio-url "$studio_url" \
       --yes
   ```

7. Report the returned Sandbox display name, session ID, remote project directory, restored file count, Git status, and whether GitHub authentication was installed. Do not start a remote task or change the remote project after restoration unless the user asks.

## Script options

Use `--project-name` to override the repository basename, `--remote-home` only when Studio supports a different home, `--handoff` to append a user-supplied Markdown handoff, and `--output` to retain a local copy of the generated project bundle. Use `--temporary` only when the user explicitly requests a non-persistent Sandbox. Use `--no-github-credentials` only when the user explicitly opts out; otherwise a GitHub remote requires working local `gh` authentication.

The live command requires `--yes`. Add `--allow-sensitive` only after explicit approval for filenames or possible secret assignments identified by the preview. GitHub credentials travel in a separate ephemeral payload, never in the retained `--output` bundle, and the remote staging payload is deleted after installation. On failure, report the safe error and whether Studio already created a session; never expose the token or returned private Sandbox endpoint.
