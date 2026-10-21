# Studio MPA AGENTS.md

[中文](README.zh.md) · [Design](../../prd-spec/features/studio-agents-md-edit/2026-10-21-studio-agents-md-edit.md)

## Ownership and scope

The MPA information rail edits the selected Runtime's document. The Studio backend
owns authorization and credential injection; Runtime owns revisions and application
to Main/Worker. This adds no model/Skill/MCP or Bot Profile editor, cache or deployment.

## Interface and security

Proxy GET/POST `/api/v1/studio/agents-md`, scoped by Runtime ID and region. Require a
Studio administrator plus existing Runtime visibility authorization. Strip incoming
`X-MPA-Studio-Key` and inject only the server-resolved current Runtime key. Reject
noncanonical path aliases. Never store that key in browser state.

GET returns `{content: string, revision: integer}`; POST accepts the same shape,
updates only the document, and returns the saved/current revision. Empty content
clears custom instructions; the limit is 40000 characters. Concurrent edits return
409, missing/invalid credentials 401/503, denied access 403, invalid body 422.
Old Runtimes may return 404/405/501; show an upgrade message and preserve metadata viewing.

## Interaction and state

Reuse ModalLayout, Button, Textarea, ScrollArea and Base UI Dialog. Load persisted
text on open; disable saving during loading/saving, when unchanged, over limit, or
when a previous save's result is uncertain. Confirm clearing or discarding edits.
Retain drafts on errors. A conflict requires refreshing and reconciling the current
revision. Network/5xx save errors require readback before another write. Prevent
repeat saves and composition-time submission; abort requests on unmount and discard
late responses. The rail remounts when the Runtime/region target changes.

## Effective configuration

Running turns keep their document snapshot. The next Main turn uses saved content, including reused conversations; clearing
removes custom Main content but retains platform rules. Worker files receive the
snapshot, but native reused Worker threads may retain old instructions. Worker
hot reload remains deferred and is not guaranteed by a successful Studio save. History is retained. The API verifies delivery of
configuration, not deterministic model behavior. Editing updates the selected
Runtime directly; ArkClaw's separate debug/publish environments are not introduced.

## Verification

Python proxy authorization/forged-header tests, Runtime persistence/CAS and turn
snapshot tests, frontend load/save/error/clear/IME/cancellation tests, browser
checks and production build. Actual results and limitations are in the paired design.
