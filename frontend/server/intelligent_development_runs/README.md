# Build result submission

New build sessions use `tool-v1`. The worker starts a Codex thread with the
`submit_build_result` dynamic function; the empty thread prepared for the UI has
not accepted user work and is not reused. Codex 0.154.0 registers dynamic tools
on `thread/start`, restores them on `thread/resume`, and replays outstanding
`item/tool/call` requests. Ordinary Sandbox chat has no callback or added tool.

The tool validates the complete reporting schema and measured verification
requirements. Studio supplies owner/run/lease identity, binds the native
thread/turn/call identifiers, and checks the model's revision echo against both
the accepted revision and queued/sending inputs. Only redacted completion
metadata and a digest of the arguments enter SQLite. Results and success replies
commit together before acknowledgement, so a replay cannot duplicate delivery.
The extra table cascades with the existing short-lived run retention.

A successful native turn consumes its saved result without reading a model-named
file or starting another development turn. Missing metadata permits one automatic
reporting turn, limited to 120 seconds, with read-only filesystem permissions,
network disabled, and instructions to reuse measured evidence. It cannot rerun
the full builder prompt. An explicit user resume can retry reporting; a new user
requirement starts its own development cycle. A failed/interrupted development
turn still follows native recovery decisions and keeps its actual metrics.

Steer messages carry an input revision and invalidate earlier submissions.
Publication checks revisions before packaging and version persistence; the final
artifact event and task completion share a SQLite transaction that rejects stop,
newer revisions, and pending/sending inputs. A concurrently superseded immutable
version may already have been saved, but it is not emitted as the current result.
Remote packaging remains reconciled through the existing deterministic delivery
ID and `RunShell` execution receipt.

The UI preserves the native turn summary while displaying artifact preparation,
version saving, or reporting recovery. Stop remains available throughout. The
artifact card appears after saving the version; preparation time is not added to
native turn or tool measurements.

Compatibility is thread-scoped: runs without a marker and existing `file-v1`
threads retain their file protocol, including follow-ups. Codex 0.154.0 cannot
add dynamic tools to an existing thread via resume. Start a new build session to
use the new protocol. The migration adds a table and per-run checkpoint marker;
it does not alter sandbox images or discard old rows. Older Studio code can read
the database but cannot execute active `tool-v1` runs: drain them before rolling
back. With the currently accepted ephemeral single-instance deployment, instance
replacement clears all short-term run records as before.
