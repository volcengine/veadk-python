---
name: agentkit-codex-handoff
description: Continue the current local Codex conversation and coding task in an AgentKit Studio cloud Codex Sandbox using a Studio URL and short one-time pairing code. Use when the user asks to hand off, migrate, or continue a local repository in Studio, especially when a prompt contains a Studio address and pairing code. Export the complete user-visible user and assistant message history from every prior turn, including interrupted turns and progress commentary, create a temporary Studio Sandbox, restore tracked and non-ignored working-tree files plus Git metadata, inject that visible history into the cloud Thread, transfer GitHub CLI authentication separately when needed, and send one final continuation message; never copy system or developer prompts, reasoning, tool logs, SQLite state, global configuration, local skills, or SSH private keys.
---

# Continue a Task in Studio

Transfer the project plus the current task's visible conversation, not the local Codex runtime. Create one temporary Studio Sandbox with the supplied pairing code, restore the project, inject the complete visible history from every prior turn into its fresh cloud Thread, then send exactly one new user message so the cloud Session continues working.

Accept a terse handoff prompt containing only the intent, Studio URL, and pairing code. When invoked immediately after Plugin installation, stay in the current Codex task, load this Skill explicitly if automatic discovery has not refreshed, and continue without asking the user to repeat the repository or task context.

## Boundaries

Include only:

- Git tracked files and non-ignored untracked files, including working-tree edits and deletions
- repository-level `AGENTS.md` files selected by the same Git rules
- Git branch, HEAD commit, sanitized remote URL, and status metadata
- a generated `HANDOFF.md`; append the generated section when the project already has one
- every user and assistant message visible in the active Codex task before the current handoff turn, including progress commentary and interrupted turns
- local PNG, JPEG, GIF, or WebP images attached to those prior user messages

Never include:

- Codex system or developer prompts, reasoning summaries, tool calls or outputs, rollout JSONL, or SQLite state
- `$CODEX_HOME`, local or global Skills, plugin caches, or global Codex settings
- SSH private keys, non-GitHub credentials, or global Git configuration
- ignored files such as `.env` unless they are deliberately tracked

Do not place conversation history in the repository, `HANDOFF.md`, retained project bundle, logs, or command output. Send it only through the authenticated one-time continuation request. Do not claim that the remote environment is an exact copy of local Codex; it is a visible-history and project handoff into a separately configured Studio runtime.

## Workflow

1. Resolve the repository from the user's `repo` value or the current working directory. Confirm it with `pwd`.
2. Resolve `studio_url` and `pairing_code` from the user's prompt. Treat the pairing code as a secret: do not print it, write it to a file, or place it in the bundle.
3. Create a concise Chinese task description for the cloud Agent name. Infer it yourself from the active task; do not ask the user to name it. Use at most 12 Unicode characters, omit punctuation and generic prefixes such as `Codex`, and describe the work rather than the repository. Examples: `完善端云接力`, `修复登录超时`, `优化订单检索`.
4. Export the active task's complete visible conversation with the Codex app task tools:
   - Call `list_threads` and select the most recently updated active Codex task whose working directory matches the repository and whose title or summary matches the current objective.
   - Identify the current handoff turn as the turn containing the pairing-code request being executed. Exclude that entire turn only; do not exclude any older turn based on `completed`, `interrupted`, failed, or other status.
   - Call `read_thread` with `includeOutputs: false`, `maxOutputCharsPerItem: 20000`, and `turnLimit: 10`. The response is `newest_first`: save its `page.nextCursor`, call `read_thread` again with that cursor whenever `page.hasMore` is true, and continue until `page.hasMore` is false or 100 eligible visible messages have been collected. Never stop after the first page merely because it contains a completed turn.
   - Reassemble pages and turns oldest-to-newest. Within each eligible turn, preserve item order and keep every `userMessage` and every `agentMessage` exactly once. Keep all user-visible assistant phases, including progress commentary before a final answer; do not merge, summarize, deduplicate, or replace them with the final answer.
   - Exclude system/developer instructions, reasoning, tool calls and outputs, approvals, environment context, and other item types. Filtering is based on item type, never on turn status or `agentMessage.phase`.
   - A delegated user message can contain an XML-looking `<codex_delegation>` wrapper. When the structured text part contains `codexDelegation.input`, use that value as the user-visible text and discard the wrapper. Never upload the wrapper or its `sourceThreadId`.
   - Preserve user images. For `localImage`, record its absolute `path`. Also recognize Markdown images whose target is an absolute local path, such as `![截图](/tmp/example.png)`, and record the path plus alt text. The bundled script removes those local Markdown links from the visible text, validates ordinary non-symlink image files, and converts the bytes in memory for the one-time request. Do not copy images into the repository, `HANDOFF.md`, bundle, logs, or command output.
   - Remove injected `<in-app-browser-context>...</in-app-browser-context>` blocks. When a user message contains `## My request:`, keep the text after that marker.
   - Preserve oldest-to-newest order and exact message boundaries. Write a temporary mode-`0600` JSON file outside the repository using schema version 2, without printing its contents:

     ```json
     {"schemaVersion":2,"messages":[{"role":"user","content":"...","images":[{"path":"/absolute/local/image.png","alt":"截图"}]},{"role":"assistant","content":"..."}]}
     ```

   - Omit `images` when a message has none. The script accepts schema version 1 for text-only compatibility, but new exports must use version 2. Before uploading, compare the JSON message count with the number of eligible `userMessage` and `agentMessage` items collected from all pages; stop on any mismatch. Stop instead of starting an empty cloud Thread when no visible messages can be exported.
5. Choose the final cloud user message. Use the user's explicit cloud instruction when one accompanies the handoff request; otherwise use exactly `继续`. Do not prepend project paths, migration explanations, or `HANDOFF.md` instructions to this visible message.
6. Create a temporary Markdown handoff outside the repository. Summarize only the current user objective, decisions, completed work, remaining work, validation results, and real blockers. Do not include system or developer prompts, conversation transcripts, credentials, or unrelated context.
7. For a GitHub remote, verify `gh auth token --hostname github.com` succeeds. GitHub authentication is transferred separately from the project bundle, installed with mode `0600`, and configured for HTTPS pushes. Never print the token. Convert an SSH-form GitHub remote to HTTPS instead of copying SSH keys.
8. Locate this Skill's `scripts/upload_current_dir.sh` and run a preview:

   ```bash
   scripts/upload_current_dir.sh \
     --repo "$PWD" \
     --studio-url "$studio_url" \
     --agent-name "$agent_name" \
     --handoff "$handoff_file" \
     --history "$history_file" \
     --continue-message "$continue_message" \
     --dry-run
   ```

9. Review the preview's file count, size, visible conversation message count, GitHub authentication status, and sensitive-file warnings.
   - If high-risk filenames or possible secret assignments are present, stop and ask whether to exclude them locally or upload them with `--allow-sensitive`.
   - If no sensitive-file warnings are present and the current user request explicitly asks to upload, that request is sufficient confirmation.
10. Run the live handoff without echoing the pairing code, conversation contents, or GitHub token:

   ```bash
   AGENTKIT_STUDIO_PAIRING_CODE="$pairing_code" \
     scripts/upload_current_dir.sh \
       --repo "$PWD" \
       --studio-url "$studio_url" \
       --agent-name "$agent_name" \
       --handoff "$handoff_file" \
       --history "$history_file" \
       --continue-message "$continue_message" \
       --yes
   ```

   Keep the command attached until it returns. Relay each `[handoff] progress:`
   line as concise progress to the user instead of waiting silently. The command
   returns after Studio confirms that the cloud Codex completed the continuation and generated a visible reply;
   the cloud task then keeps running independently.

11. Delete the temporary history and handoff files after the command returns. Confirm that the script created a temporary Studio Sandbox, restored the project, injected the visible conversation history and images, and sent the final continuation message. Report the Sandbox display name, session ID, remote project directory, restored file count, imported message count, imported image count, Git status, GitHub authentication result, and continuation status. Do not claim success when the continuation stream reports an error or closes before completion.

## Script options

`--agent-name` is required for a live handoff and controls only the cloud Agent name. `--history` is required and accepts only the versioned visible-message JSON described above. Images are limited to 10 supported files, 4 MiB per image, and 8 MiB total. `--continue-message` defaults to `继续`. `--project-name` controls the bundle and remote directory and defaults to the repository basename. Use `--remote-home` only when Studio supports a different home, `--handoff` to append the task summary, and `--output` to retain a local copy of the generated project bundle. The script always creates a temporary Studio Sandbox. Use `--no-github-credentials` only when the user explicitly opts out; otherwise a GitHub remote requires working local `gh` authentication.

The live command requires `--yes`. Add `--allow-sensitive` only after explicit approval for filenames or possible secret assignments identified by the preview. Visible history travels in the one-time Studio request and is injected with `thread/inject_items` before the final `turn/start`; old messages must never be replayed as turns. GitHub credentials travel in a separate ephemeral payload, never in the retained `--output` bundle, and the remote staging payload is deleted after installation. On failure, report the safe error and whether Studio already created a Session; never expose the pairing code, conversation contents, token, or returned private Sandbox endpoint.

Large project bundles are uploaded in bounded parts, reassembled in order, and verified by SHA-256 before restore. If upload or restore fails after Session creation, the script reports the failed stage to Studio and a retry with the same pairing code resumes the existing Session instead of creating another one. Reuse the original pairing code for that retry while it remains valid.
