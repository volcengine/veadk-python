# Dynamic legacy skills

The existing `Agent(skills=[local_directory, space_id], skills_mode="local",
enable_dynamic_load_skills=True)` option registers `check_skills` as a before-agent
callback. Its default remains false. It works without a sandbox subclass.

Each callback reads the current `Agent.skills`, including replaced directories,
added/removed spaces, and an empty list. Comma-separated spaces use the existing
provider routing. Provider versions remain authoritative; there is no additional
client-side latest-version policy.

State is held by the existing SkillsToolset instance, with its baseline recorded
during initialization. Changes include local SKILL.md content, source identity,
package path, bucket, version and metadata. A path-only change replaces execution
tools without rewriting an otherwise identical skills prompt. Stable name ordering
avoids prompt churn when a provider reorders results. The base instruction and
other callback text are preserved, including callable instructions.

A failed source retains its previous successful result; successful empty responses
remove it. Sources removed from configuration cannot reappear from retained state.
`SkillsToolset.status()` reports safe error types and loaded names/IDs/versions.
The next successful refresh clears failures. Tool construction finishes before the
new skill dictionary, checklist view and tools are published.

Applications can subclass SkillsToolset's named `prepare_skills`, `wrap_tool`,
and `on_source_error` methods to adapt results and instrumentation. Rebuilding tools
uses the same instance, so instrumentation is preserved. There are no new Agent
callable parameters, execution overrides, or runtime binding/discovery components.

This callback does **not** lock the full execution of a shared Agent. Applications
that run a mutable Agent concurrently must coordinate that execution themselves.
The Playground sandbox does so in its own SkillSandboxAgent. Realtime/live flows,
arbitrary local script writes, and remote objects overwritten without any locator
or metadata change are not snapshotted. Prompt stability is not a guarantee of
provider-side prefix-cache hits, and earlier conversation messages are not rewritten.

## Downloaded archive layout

Space and SkillHub archives are downloaded and extracted in a temporary directory.
Both a root `SKILL.md` and a wrapping directory containing `SKILL.md` install as
`skills/<skill_name>/SKILL.md`, with resources alongside it. The root file takes
precedence; otherwise the shallowest candidate wins, with path order breaking
ties. Multiple candidates and deeper layouts produce a warning rather than a
rejection. Only the selected skill root and its descendants are installed.

Extraction and UTF-8 readability checks finish before an existing installation
is moved aside. A failed replacement restores the old installation. ZIPs and
staging files are cleaned on success and failure; successful installs also remove
the legacy `skills/<skill_name>.zip`. Layout selection, destination, fallback,
success, and failure are logged. A failed rollback retains a backup and logs its
location. This does not provide cross-process atomicity or crash recovery.

Skill names remain the installation key; this does not change duplicate-name
selection or remove files spilled into the shared skills directory by old versions.
