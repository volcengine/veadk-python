# MPA Runtime task viewer

[中文版](README.zh.md)

2026-09-15. The Studio panel owns read-only presentation and pagination of the selected Runtime's /api/v1/esa-cron-tasks response. MPA owns storage, user authorization and scheduling. The existing Studio proxy owns Runtime access and gateway authentication. Selection includes Runtime ID and region; no selection performs no requests. Requests use limit=20, offset and includeDisabled=true. The optional X-Jwt-Token lives only in component memory and is cleared when the target changes or panel unmounts. Lists display only tasks accessible to that token. Errors never become empty successes, and stale responses must not cross targets. No mutation or scheduler APIs are added. See [change and verification](../../prd-spec/features/studio-mpa-cron-tasks/README.md).
