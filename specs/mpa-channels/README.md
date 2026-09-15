# MPA channels

[中文](README.zh.md)

## Contract

Studio administrators manage MPA channels through the existing Runtime proxy. The BFF strips incoming X-MPA-Channel-Key, requires admin authorization for all api/v1/channels paths, refuses events ingress through Studio, and injects the resolved Runtime API key for management. MPA opts in via CHANNEL_ADMIN_AUTH_MODE=runtime_key; default JWT remains available. Missing runtime keys fail closed. CHANNEL_STATE_ENCRYPTION_KEY must be provisioned once and retained across image updates; it is secret configuration.

GET /api/v1/channels/capabilities returns serverSideBinding, bindingReady, bindingError and diagnostics support. Missing capabilities (404) means unsupported. POST /feishu/bindings creates an encrypted durable binding; GET /feishu/bindings/{id} advances it; POST /feishu/bindings/{id}/retry retries failure. Prefix these paths with /api/v1/channels. States are PENDING, SCANNED, AUTHORIZED, REGISTERING, BOUND, FAILED, EXPIRED. Responses contain id, loginUrl, qrCodeImage, expiresAt, pollAfterSeconds, appId, lastErrorCode and lastErrorMessage. Credentials never appear. A lost registration lease reports uncertainty instead of blindly repeating registration.

GET /feishu/diagnostics reports actual stored configuration, missing metadata and observed delivery state. Existing GET /chat-permissions, POST /chat-permissions and DELETE /chat-permissions?channel=feishu&chat_id=... manage groups. POST uses channel, chatId and groupSessionScope (group, group_sender, group_topic, group_topic_sender). Existing DELETE root uses channel and appId. Binding and polling requests are cancelled on navigation; errors preserve the form, terminal states stop polling. Unsupported images show an upgrade message. No success indicator claims live connectivity without observed evidence.

Database boundary: each MPA/formal-debug deployment needs an isolated channel database; startup rejects sharing across deployments. New message mappings include bot identity; old sessions remain history without automatic context migration. New ciphertext is not compatible with old images; rollback requires a matching database snapshot. Studio forwards only the trusted administrator identity as binding owner, replacing client X-User-Id. Runtime-key event ingress validates Authorization injected by APIG.


## Studio navigation
Message channels is a dedicated Agent detail section alongside Integrations and Versions. Feishu, WeCom and DingTalk are distinct provider categories. Only implemented provider flows expose setup actions; unavailable providers are explicitly labeled. Gateway/route configuration and observed delivery retain distinct semantics. See [workspace design](../../prd-spec/features/message-channel-workspace/2026-09-15-message-channel-workspace.md).

## Multi-provider binding (2026-09-15)

CON-8: Studio Message channels enables Feishu, DingTalk and WeCom when Runtime capabilities advertise the provider. DingTalk exposes POST `/dingtalk/bindings`, GET `/dingtalk/bindings/{id}`, POST `/dingtalk/bindings/{id}/retry` with the same secret-free durable binding shape as Feishu. Binding IDs are provider- and owner-scoped. WeCom exposes POST `/wecom/bindings` with `{botId, secret}` and returns `{status: "BOUND", appId}` only after registration and encrypted storage. Every endpoint requires channel admin authentication. Blank credentials are rejected; remote errors are sanitized. Neither browser persistence nor responses may contain secrets.

CON-9: GET `/{channel}/diagnostics` and existing DELETE channel APIs operate on the selected provider. Studio requests chat-permissions only for Feishu; legacy non-Feishu permission endpoints remain compatible but do not control group admission. Unsupported Runtime versions require upgrading; no fallback to secret-returning legacy QR endpoints. Provider switches abort frontend work. Ambiguous registration requires Gateway inspection before a new binding; identical persisted credentials reuse the bot. Delivery observations are filtered by Gateway bot ID. Historical unscoped observations are not attributed to a provider.

Design: [message-channel-binding](../../prd-spec/features/message-channel-binding/2026-09-15-message-channel-binding.md).

CON-10: Group admission allowlists and Studio group-permission controls apply only to Feishu. DingTalk and WeCom group messages are accepted without local group-permission records, after existing authentication and bot-binding checks. Group session isolation is unchanged.

CON-11: WeCom additionally supports official SDK popup authorization; returned credentials are submitted to `/wecom/bindings` and never persisted in the browser. Popup attempts are cancelled on navigation and bounded to five minutes. DingTalk supports manual `{clientId, clientSecret}` via POST `/dingtalk/bindings/manual`, advertised by `credentialBindingChannels`, with admin authentication, encrypted storage, sanitized errors and 409 for uncertain registration. QR binding remains unchanged. Both credential routes return only `{status: "BOUND", appId}` on success. See [authorization design](../../prd-spec/features/channel-auth-methods/2026-09-15-channel-auth-methods.md).

CON-11: Configured Feishu and DingTalk channels allow QR regeneration through the existing POST binding endpoint. The pairing panel explains Feishu replacement and existing/new bot selection in provider authorization. QR creation never deletes the current binding; the summary changes only after successful BOUND diagnostics. Active pairing/loading/uncertain states prevent duplicate generation.

CON-12: Configured WeCom bots also expose Regenerate QR code. This reopens the existing SDK authorization window from the user gesture, displays pairing/replacement guidance, and saves the authorized bot through `/wecom/bindings`. Failed or cancelled authorization does not delete the existing binding.

CON-13: Pairing QR display and polling are transient to the mounted provider panel. Channel/page navigation, browser reload and panel Refresh discard pairing UI; persisted binding IDs are no longer resumed and legacy keys are cleaned. Existing bot configuration is still fetched. PENDING waiting text and the authorization-page link are hidden. Server-side binding state/expiry is unchanged; UI dismissal is not revocation.

CON-14: Agent detail Message channels is available only for a selected Runtime with agentCategory=mpa. Runtime list category metadata is propagated through cards and detail entries; an older list response can use its explicit request filter. General, unknown and local entries hide the section and never mount RuntimeChannels. An unsupported channels selection falls back to basic.

## Configuration modes (2026-09-15)

CON-15: All providers expose mutually exclusive Quick setup / Manual setup, defaulting to Quick setup on mount/provider/Runtime changes without persistence or automatic authorization. Manual Feishu uses POST `/api/v1/channels/feishu/bindings/manual` with `{appId, appSecret}` when `credentialBindingChannels` includes `feishu`; successful registration returns `{status: "BOUND", appId}` without credentials. Existing DingTalk/WeCom routes remain compatible. Both modes support configured bot replacement without first deleting the current binding. Method switches clear transient pairing/credentials, cancel frontend polling/SDK work and ignore late results; registration mutations prevent switching, and uncertain registration blocks new attempts across modes. Unsupported manual capability shows an upgrade message. The design and verification mapping are in [configuration modes](../../prd-spec/features/channel-configuration-modes/2026-09-15-channel-configuration-modes.md).
