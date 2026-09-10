# Studio release notifications

An authenticated VeFaaS HTTPS endpoint broadcasts the approved release card to
all groups joined by the Feishu application bot. No group IDs are configured in
GitHub. Add the bot to a group to subscribe it to future releases.

The `notify` job runs only after **both** Volcengine and BytePlus publishing jobs
succeed. It is separate from publication, so a notification failure does not
roll back a published version. The card contains the version, date and one list
of updates, with no environment label. Chinese and English semicolons and
newlines separate updates; empty entries are ignored. Markup in input is escaped.

## Deployment

Run from the repository root with the development dependencies installed:

```sh
python -m frontend.service.studio_release_notifier.deploy
```

Provide `VOLCENGINE_ACCESS_KEY`, `VOLCENGINE_SECRET_KEY` and, for temporary
credentials, `VOLCENGINE_SESSION_TOKEN` through the local environment.
The runtime needs `FEISHU_APP_ID`, `FEISHU_APP_SECRET`,
`STUDIO_RELEASE_WEBHOOK_KEY` (at least 32 characters) and
`NOTIFIER_PREVIEW_USER_ID` (the operator's open ID for this application).
Never commit these values.

The deployment creates or updates `veadk-studio-release-notifier` in cn-beijing,
with description `勿删：Studio 发版飞书群通知 Webhook`. It creates a dedicated
IAM role restricted to notification records under the existing `veadk-studio`
TOS bucket. Runtime cloud credentials come from VeFaaS IAM, not deployment AK/SK.
The function uses 1 vCPU and 2 GiB memory and a separate HTTPS gateway service.

Configure these GitHub repository or `studio-release` environment secrets:

| Name | Value |
| --- | --- |
| `STUDIO_RELEASE_WEBHOOK_URL` | The deployed HTTPS endpoint followed by `/release` |
| `STUDIO_RELEASE_WEBHOOK_KEY` | The same key configured in the function |

The Feishu app needs bot messaging and joined-group read permissions. The bot
must be available to the intended users and added to each target group.

## Endpoint contract

All endpoints require the `X-API-Key` header:

- `GET /readyz`: checks IAM credentials and access to notification storage
- `GET /groups`: lists groups joined by the bot
- `POST /preview`: sends a sample only to the configured operator
- `POST /release`: broadcasts a real release

POST bodies contain `version`, `date` (`YYYY.MM.DD`) and `changelog` (a string
or array of strings). Preview cards explicitly identify sample content.
Empty or oversized changelogs are rejected. With no groups, `/release` returns
409 and does not mark the release delivered.

A release's first request snapshots its recipient groups and content. Retries
must preserve that version, date and content; conflicting content returns 409.
New groups receive future releases, not historical retry notifications.
Each successful group's message ID is persisted in TOS. Transient failures
return 502, allowing the pipeline to retry only unfinished deliveries.
Concurrent retries use the same Feishu UUID for each version/group pair.

Feishu's UUID deduplication lasts one hour. If a delivery is still ambiguous
near that limit, its status becomes `needs_review` and automatic retries stop
for that group to avoid duplicates. Check whether the group received the message
before repairing the corresponding TOS record. Do not delete delivery records
or change the version just to retry a failed request.
