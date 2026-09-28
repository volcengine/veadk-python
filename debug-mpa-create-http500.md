# Debug Session: mpa-create-http500
- **Status**: [OPEN]
- **Issue**: Deployed Studio returns HTTP 500 when submitting the three-step MPA creation form with optional OpenViking configuration.
- **Debug Server**: Pending
- **Log File**: `.dbg/trae-debug-log-mpa-create-http500.ndjson`

## Reproduction Steps
1. Open the deployed Studio MPA creation dialog.
2. Complete Basic Information and Database.
3. Complete all three OpenViking fields or leave them blank.
4. Submit creation.
5. Observe `HTTP 500`.

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | The task store uses the read-only deployed code directory. | High | Low | Confirmed in an equivalent read-only runtime reproduction. |
| B | A remaining task or child-process path rejects `config_path=None`. | Medium | Low | Rejected for the synchronous 500; submission reached task-store initialization. |
| C | The transient OpenViking secret field does not match the deployed request model. | Medium | Low | Rejected; all three fields passed request and resource validation. |
| D | Cloud IAM credentials pass inspection but fail during task submission. | Medium | Medium | Not reached by the reproduced failure. |
| E | The frontend replaces a structured server error with generic `HTTP 500`. | Medium | Low | Rejected; the server returns an unhandled 500 before creating a task. |

## Log Evidence
- `.dbg/trae-debug-log-mpa-create-http500.ndjson:1`: the request reached task submission with the built-in profile (`configPathIsNone=true`) and all three OpenViking inputs present.
- `.dbg/trae-debug-log-mpa-create-http500.ndjson:2`: default task path `.adk/mpa-creation.sqlite3` had a missing, non-writable parent in a read-only runtime directory.
- The next `task-store-after` event was absent and the route returned `500 Internal Server Error`, locating the exception in `CreationTasks(task_path)`.
- Deployment setup does not set `VEADK_MPA_TASK_DB`; the built-in profile also leaves `bootstrap-path` at `.adk/mpa-pg-bootstrap.sqlite3`, so a task-store-only `/tmp` override would expose a second write-path failure.

## Verification Conclusion
Pre-fix reproduction matches the deployed HTTP status. The immediate root cause is a relative SQLite task path under the read-only VeFaaS code directory. A complete fix must also move the bootstrap SQLite path and preserve the documented cross-restart/single-coordinator semantics; using ephemeral `/tmp` alone would violate that contract.
