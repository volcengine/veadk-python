---
name: codex-sandbox-upload
description: Continue the current local coding task in an AgentKit Studio cloud Codex Sandbox using a Studio URL and short one-time pairing code. Use when the user asks to hand off, migrate, or continue a local repository in Studio, especially when a prompt contains a Studio address and pairing code. Summarize the active task into HANDOFF.md, create a temporary Studio Sandbox, restore tracked and non-ignored working-tree files plus Git metadata, transfer GitHub CLI authentication separately when needed, and send the cloud Session a continuation message; never copy Codex system prompts, conversations, SQLite state, global configuration, local skills, or SSH private keys.
---

# Continue a Task in Studio

Transfer the project and a concise task handoff, not the local Codex runtime. Create one temporary Studio Sandbox with the supplied pairing code, restore the project, then send the continuation message so the cloud Session starts working.

Accept a terse handoff prompt containing only the intent, Studio URL, and pairing code. When invoked immediately after Plugin installation, stay in the current Codex task, load this Skill explicitly if automatic discovery has not refreshed, and continue without asking the user to repeat the repository or task context.

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
2. Resolve `studio_url` and `pairing_code` from the user's prompt. Treat the pairing code as a secret: do not print it, write it to a file, or place it in the bundle.
3. Create a concise Chinese task description for the cloud Agent name. Infer it yourself from the active task; do not ask the user to name it. Use at most 12 Unicode characters, omit punctuation and generic prefixes such as `Codex`, and describe the work rather than the repository. Examples: `完善端云接力`, `修复登录超时`, `优化订单检索`.
4. Create a temporary Markdown handoff outside the repository. Summarize only the current user objective, decisions, completed work, remaining work, validation results, and real blockers. Do not include system or developer prompts, conversation transcripts, credentials, or unrelated context.
5. For a GitHub remote, verify `gh auth token --hostname github.com` succeeds. GitHub authentication is transferred separately from the project bundle, installed with mode `0600`, and configured for HTTPS pushes. Never print the token. Convert an SSH-form GitHub remote to HTTPS instead of copying SSH keys.
6. Locate this Skill's `scripts/upload_current_dir.sh` and run a preview:

   ```bash
   scripts/upload_current_dir.sh \
     --repo "$PWD" \
     --studio-url "$studio_url" \
     --agent-name "$agent_name" \
     --handoff "$handoff_file" \
     --dry-run
   ```

7. Review the preview's file count, size, GitHub authentication status, and sensitive-file warnings.
   - If high-risk filenames or possible secret assignments are present, stop and ask whether to exclude them locally or upload them with `--allow-sensitive`.
   - If no sensitive-file warnings are present and the current user request explicitly asks to upload, that request is sufficient confirmation.
8. Run the live handoff without echoing the pairing code or GitHub token:

   ```bash
   AGENTKIT_STUDIO_PAIRING_CODE="$pairing_code" \
     scripts/upload_current_dir.sh \
       --repo "$PWD" \
       --studio-url "$studio_url" \
       --agent-name "$agent_name" \
       --handoff "$handoff_file" \
       --yes
   ```

   Keep the command attached until it returns. Relay each `[handoff] progress:`
   line as concise progress to the user instead of waiting silently. The command
   returns after Studio confirms that the cloud Codex accepted the continuation;
   the cloud task then keeps running independently.

9. Confirm that the script created a temporary Studio Sandbox, restored the project, and sent the continuation message. Report the Sandbox display name, session ID, remote project directory, restored file count, Git status, GitHub authentication result, and continuation status. Do not claim success when the continuation stream reports an error or closes before completion.

## Script options

`--agent-name` is required for a live handoff and controls only the cloud Agent name. `--project-name` controls the bundle and remote directory and defaults to the repository basename. Use `--remote-home` only when Studio supports a different home, `--handoff` to append the task summary, and `--output` to retain a local copy of the generated project bundle. The script always creates a temporary Studio Sandbox. Use `--no-github-credentials` only when the user explicitly opts out; otherwise a GitHub remote requires working local `gh` authentication.

The live command requires `--yes`. Add `--allow-sensitive` only after explicit approval for filenames or possible secret assignments identified by the preview. GitHub credentials travel in a separate ephemeral payload, never in the retained `--output` bundle, and the remote staging payload is deleted after installation. On failure, report the safe error and whether Studio already created a Session; never expose the pairing code, token, or returned private Sandbox endpoint.
