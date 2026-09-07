# Studio workflow matrix

This local fixture exposes six applications for checking Studio rendering:

- `llm_agent`
- `sequential_agent`
- `parallel_agent`
- `loop_agent`
- `mixed_agent`
- `all_agent_types_agent`

Start Studio from the repository root with the agents directory set to
`examples/studio_workflow_matrix`, then send the same prompt to each app:

> 请分析团队是否应该采用每周四天工作制，并明确列出事实、风险和建议

The first five fixtures use stable markers so fragmented or duplicated cards are easy
to spot. `all_agent_types_agent` combines LLM, Sequential, Parallel, and Loop agents
while keeping all user-facing output natural and free of artificial test markers. Its
Parallel stage has four specialists so the wide-screen three-column viewport and
horizontal overflow can be exercised in one end-to-end run.
