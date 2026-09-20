"""Provision one persistent Skill Space per logical agent during deployment."""

from __future__ import annotations

from veadk.integrations.mpa.managed.database import DeploymentError, agent_suffix


async def ensure_skill_space(
    entry,
    cloud,
    *,
    account,
    region,
    agent_id,
    project_name="",
    configured_id="",
    current_id="",
):
    """Caller holds the deployment lock. Never replace a missing registered space.

    CreateSkillSpace has no ClientToken. Persist the intent first and recover a
    lost response by exact name and ownership tags; never blindly repeat create.
    """
    record = await entry.read()
    registered_id = record.get("skill_space_id", "")
    ids = {value for value in (registered_id, configured_id, current_id) if value}
    if len(ids) > 1:
        raise DeploymentError(
            "Runtime, template and registered Skill Space differ; migrate explicitly"
        )
    if ids:
        space_id = ids.pop()
        space = await cloud.get_skill_space(space_id)
        validate_space(space, space_id, project_name)
        if record.get("skill_space_managed"):
            validate_owned_space(space, record["skill_space_request"])
        record.update(skill_space_id=space_id, skill_space_name=space.get("Name", ""))
        record.setdefault("skill_space_managed", False)
        await entry.save(record)
        return space_id

    if record.get("pending"):
        raise DeploymentError(
            "Finish the previous deployment before adding a Skill Space"
        )
    suffix = agent_suffix(account, region, agent_id)
    request = {
        "Name": "mpa_skills_" + suffix,
        "Description": "Skills for MPA agent " + agent_id,
        "Tags": [
            {"Key": "managed_by", "Value": "mpa-deployment"},
            {"Key": "mpa_agent_key", "Value": suffix},
            {"Key": "display_name", "Value": agent_id + " 技能空间"},
        ],
    }
    if project_name:
        request["ProjectName"] = project_name
    previous = record.get("skill_space_request")
    if previous and previous != request:
        raise DeploymentError(
            "Unfinished Skill Space creation has different inputs; resume its original configuration"
        )
    spaces = await cloud.find_skill_spaces(request["Name"], project_name)
    if spaces:
        if len(spaces) != 1 or not record.get("skill_space_create_requested"):
            raise DeploymentError(
                "Skill Space name already exists without a unique recorded creation intent"
            )
        space = spaces[0]
        validate_owned_space(space, request)
        space_id = space.get("Id", "")
        validate_space(space, space_id, project_name)
    else:
        if record.get("skill_space_create_requested"):
            raise DeploymentError(
                "Skill Space creation outcome is unknown; retry discovery later or verify cloud resources "
                "before clearing skill_space_create_requested in the deployment registry"
            )
        record.update(skill_space_request=request, skill_space_create_requested=True)
        await entry.save(record)
        space_id = await cloud.create_skill_space(request)
        if not space_id:
            raise DeploymentError(
                "CreateSkillSpace returned no ID; rerun to discover the existing space"
            )
    # Save the ID immediately, before Runtime creation or eventual-consistency reads.
    record.update(
        skill_space_id=space_id,
        skill_space_name=request["Name"],
        skill_space_managed=True,
    )
    await entry.save(record)
    return space_id


def validate_space(space, space_id, project_name):
    if not space_id or space.get("Id") != space_id:
        raise DeploymentError(
            "Skill Space is missing; restore its binding instead of creating an empty replacement"
        )
    if str(space.get("Status", "")).lower() in {
        "failed",
        "error",
        "deleting",
        "deleted",
    }:
        raise DeploymentError(
            "Skill Space is unavailable; inspect its status before deploying"
        )
    if project_name and space.get("ProjectName") != project_name:
        raise DeploymentError("Skill Space belongs to a different project")


def validate_owned_space(space, request):
    tags = {t["Key"]: t.get("Value", "") for t in space.get("Tags") or []}
    expected = {t["Key"]: t["Value"] for t in request["Tags"]}
    if space.get("Name") != request["Name"] or any(
        tags.get(key) != expected[key] for key in ("managed_by", "mpa_agent_key")
    ):
        raise DeploymentError(
            "Skill Space ownership does not match this agent; refusing adoption"
        )
