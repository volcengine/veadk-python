# mpa-agent Studio A2A Streaming Verification Cases

## Environment

- mpa-agent branch: `fix/a2a-studio-streaming`
- veadk-python branch: `feat/mpa-agent-oneclick-provision`
- Test Runtime: `r-yeuujrrcowb21078p9jh`
- Studio: `http://127.0.0.1:8001`
- Evidence directory: `.artifacts/a2a-streaming/` in each repository; secrets are prohibited.

## Cases

| Case | Coverage | Preconditions and action | Expected result | Evidence |
| --- | --- | --- | --- | --- |
| `VC-1` | FR-1 | curl the agent card | `capabilities.streaming=true` | `agent-card.json` |
| `VC-2` | FR-2/3/5 | Raw `message/stream` runs `sleep 2; echo step-1; sleep 2; echo step-2` | working, tool events, and timed output arrive before completion | `raw-a2a-stream.jsonl`, timestamp log |
| `VC-3` | FR-2/5 | Run VC-2 through Studio `/run_sse` | Browser stream receives progress and deltas before completion | `studio-stream.txt`, screenshot |
| `VC-4` | FR-4 | Count terminal/final events for one execution | One terminal and one final body | `terminal-count.txt` |
| `VC-5` | FR-6 | Mock a card without streaming capability | Exactly one `message/send` call | pytest output |
| `VC-6` | FR-6 | Mock pre-event method-not-supported | One fallback only; one task creation | pytest output |
| `VC-7` | FR-6/7 | Disconnect Studio after first event | No second request; original task completes | Request count and task JSON |
| `VC-8` | FR-7 | Refresh the original session after VC-7 | Final result is readable; missed deltas need not replay | Studio screenshot and task JSON |
| `VC-9` | FR-8 | Slow consumer with many deltas | Text may coalesce; tool result and terminal remain | pytest output |
| `VC-10` | FR-9 | Scan all streamed payloads | No API key, Authorization, full env, or signed URL | Secret-scan output |
| `VC-11` | FR-10 | Connect to a legacy non-streaming Runtime | Blocking mode still returns final text | `legacy-runtime.txt` |
| `VC-12` | FR-10 | Exercise Web, Feishu DM/group/group-add, and scheduled tasks | Behavior remains unchanged | Regression logs; mark blocked if external prerequisites are unavailable |
| `VC-13` | FR-3/5 | Run different markers in two concurrent Studio sessions | Distinct sandbox/session and no cross-streaming | `concurrent-streams/` |
| `VC-14` | FR-4/7 | Cancel during streaming | One canceled terminal and downstream cancellation | cancel JSONL |
| `VC-15` | FR-2/5 | Direct model answer | Text streams without sandbox events | `direct-answer-stream.txt` |

## Execution order and failure handling

1. Unit tests cover VC-1, VC-4 through VC-6, VC-9, and VC-10.
2. Local integration covers VC-2, VC-3, VC-11, and VC-15.
3. The test Runtime covers VC-2 through VC-4, VC-7, VC-8, VC-13, and VC-14.
4. Run VC-12 last to avoid touching external channels before protocol stability.
5. Any P0/P1 case failure returns the loop to TDD implementation and blocks review.

## Execution result (2026-09-12)

- `VC-1`–`VC-11`, `VC-13`, and `VC-15`: pass against Runtime version 31 (`mpa_agent:a2a-v8`) and Studio `127.0.0.1:8001`.
- `VC-12`: automated Web/Feishu/scheduling/group-bot regression paths pass; live Feishu delivery is blocked by unavailable bot credentials and installation target.
- `VC-14`: cancellation and single-terminal ownership pass in the executor regression suite; no additional live destructive cancel was required after the earlier disconnect proof.
- Sandbox timeline: tool call 20.23s, output 22.87s, text delta 26.51s, final 27.44s. Refresh returned the complete `v31-final-1` / `v31-final-2` result.
- Concurrent run: 25 and 26 frames, distinct invocation IDs, no marker leakage.
- Direct answer: true ADK deltas are forwarded; a cumulative working snapshot is suppressed and a single durable final remains. Delta granularity is controlled by the upstream model/ADK implementation.
- Secret scan: 13 evidence files, zero matches for supplied PostgreSQL/OpenViking credentials, Authorization headers, or API-key patterns.
- Frontend package command is environment-blocked because this checkout lacks `vite`, `esbuild`, and `typescript`; Python bridge tests pass.
