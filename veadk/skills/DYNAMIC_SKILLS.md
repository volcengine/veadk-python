# Dynamic local-execution skills

`Agent(skills=[local_directory, space_id], skills_mode="local",
enable_dynamic_load_skills=True)` refreshes configured sources before each
invocation. The default remains false. Comma-separated spaces and provider
routing use the existing loader. Space versions are provider-bound versions,
not an independent client-side latest-version policy.

An instance lock covers the complete async event stream, including callbacks
and closure. Agents do not share refresh state. This is not a cross-process
filesystem lock. Realtime/live execution is not covered.

Metadata and package-locator changes construct a candidate Toolset before
publication. Unchanged results retain the tools. Names render in stable order;
version-only changes do not add generation IDs or timestamps to the prompt.
Local SKILL.md content changes invalidate the execution view; arbitrary scripts
and concurrent filesystem writes are not snapshotted. The prompt asks the model
to reload instructions each turn; conversation history is not rewritten. Prompt
stability alone does not establish provider-side prefix-cache hits.

A failed SDK source retains its previous result by default, exposing a sanitized
entry in `agent.skills_status["issues"]`. Use
`skills_refresh_failure_policy="omit"` to omit it instead. A successful empty
result removes the source's skills. Initial failures have nothing to retain.

## External results and instrumentation

`skills_transform` accepts a synchronous or asynchronous callable:

```python
async def merge_skills(sdk_skills, invocation_context):
    return combine(sdk_skills, await external_source.refresh())

agent = Agent(
    name="example",
    skills=["/path/to/skills", "ss-example"],
    skills_mode="local",
    enable_dynamic_load_skills=True,
    skills_transform=merge_skills,
    skill_tool_wrapper=instrument_tool,
)
```

The transform receives copies of SDK Skill objects and returns the complete
merged list before one publication. It runs every invocation, even if SDK-source
refresh is disabled, and owns external-source precedence/errors. Duplicate names
are rejected. Transform or wrapper errors abort preparation before publication.
Construction prepares only SDK sources; external transforms first run at
invocation time.

`skill_tool_wrapper(tool)` returns a BaseTool and runs on every new Toolset,
keeping instrumentation after refresh. Preserve names, declarations and behavior.
The public SkillsToolset constructor also accepts `tool_wrapper=`. No private
tool dictionary mutation or monkey patch is needed.

These hooks apply to the legacy local-execution SkillsToolset path, not arbitrary
tools or ADK SkillRegistry implementations.
