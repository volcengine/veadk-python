# ADK-Compatible Skill Migration

Use this reference whenever the source project contains business skills. A source business skill is project-owned material that describes workflows, domain rules, knowledge, prompts, assets, scripts, or diagnostic capabilities. Typical locations include `.codebuddy/skills/*`, `skills/*`, or any source-owned directory with `SKILL.md`.

Do not treat runtime or agent-executor skill directories as source business skills. In particular, ignore `.codex/skills/*`; those are Codex runtime skills, not the user's source project contract.

## Detection

Run `scripts/detect_source_capabilities.py` first and read `skills.items` from `source_capabilities.json`. Also inspect the source manually; detector output is evidence, not a substitute for source understanding.

For each detected skill, record:

- `SKILL.md` frontmatter: `name`, `description`
- `references/`: runbooks, examples, prompts, SQL, manuals
- `assets/`: templates, schemas, static files
- `scripts/`: source scripts and their required env/config
- `config/`: config examples and env names
- external systems required by the skill
- read/write boundary and safety constraints

Never copy plaintext secrets, cache files, logs, credentials, virtualenvs, or bytecode.

## Target Layout

Create one ADK-compatible local skill package per source business skill:

```text
skills/<skill-name>/
  SKILL.md
  references/
  assets/
  scripts/
  config/
```

Rules:

- `<skill-name>` must be filename-safe and should preserve the source `name:` when valid.
- `SKILL.md` must have frontmatter with `name:` and `description:`.
- The directory name must exactly match `SKILL.md` `name:` so `load_skill_from_dir()` can load it predictably.
- Preserve `references/`, `assets/`, `scripts/`, and `config/` when they are non-secret and useful for behavior preservation.
- Keep large content in skill resources. Do not paste full skill bodies or large references into `assistant/agent.py` instruction.

## Agent Wiring

Mount generated local skills from `assistant/agent.py` through ADK `SkillToolset`:

```python
from pathlib import Path

from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_local_skill_toolset() -> SkillToolset | None:
    skill_dirs = sorted((PROJECT_ROOT / "skills").glob("*/SKILL.md"))
    skills = [load_skill_from_dir(path.parent) for path in skill_dirs]
    if not skills:
        return None
    return SkillToolset(
        skills=skills,
        tool_filter=["list_skills", "load_skill", "load_skill_resource"],
    )
```

Then add it to the agent tools:

```python
tools = []
local_skill_toolset = _build_local_skill_toolset()
if local_skill_toolset is not None:
    tools.append(local_skill_toolset)

root_agent = Agent(
    name="...",
    instruction="...",
    tools=tools,
    # keep existing model, tracing, and safety callback config
)
```

## Scripts Boundary

If a source skill contains `scripts/`, preserve the scripts as resources by default, but do not expose arbitrary script execution by default.

Default safe mode:

```python
SkillToolset(
    skills=skills,
    tool_filter=["list_skills", "load_skill", "load_skill_resource"],
)
```

Only expose script execution when the generated project defines an explicit `code_executor` boundary or an equivalent allowlist with:

- exact executable/script allowlist
- path containment checks
- no plaintext credential forwarding
- no uncontrolled shell or network access
- clear env/config requirements
- honest failure when credentials, network, or permissions are missing

## Behavior Contract And Reports

Reflect the skill migration in:

- `source_behavior_contract.json.migration_mapping.knowledge`
- `source_behavior_contract.json.tools_and_integrations`
- `migration_metadata.json.skills_detected`
- `convert_report.md`
- `eval/cases.json` with at least one source-specific skill/tool capability case when skills exist

If a source skill cannot be fully executed after migration, preserve its knowledge/resources and report the degraded execution path. Do not claim external systems were queried unless the generated project actually can query them with configured credentials.

## Validation

Before reporting success:

```bash
python - <<'PY'
from pathlib import Path
from google.adk.skills import load_skill_from_dir

for skill_md in sorted(Path("skills").glob("*/SKILL.md")):
    skill = load_skill_from_dir(skill_md.parent)
    assert skill.name == skill_md.parent.name
    print(skill.name)
PY
```

`validate_runtime.sh` also checks:

- source-detected business skills are materialized under `skills/*/SKILL.md`
- `assistant/agent.py` uses `load_skill_from_dir` and `SkillToolset`
- generated skills are ADK-loadable
- generated skill scripts are not executable by default unless an explicit execution boundary exists
