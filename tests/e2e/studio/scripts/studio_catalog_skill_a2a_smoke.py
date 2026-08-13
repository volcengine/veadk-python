#!/usr/bin/env python3
"""Smoke-test Studio Skill Space and A2A catalog workflows."""

from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from studio_shared_workflows import (
    SmokeError,
    StepLogger,
    StudioClient,
    assert_generated_contains,
    build_basic_draft,
    deep_get,
    default_config_path,
    deploy_connect_chat,
    dry_summary,
    generate_project_for_winner,
    load_config,
    print_json,
    truthy,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "catalog_skill_a2a.local.yaml")


def choose_item(items: list[dict[str, Any]], *, id_key: str, wanted_id: str = "", name_contains: str = "") -> dict[str, Any]:
    if not items:
        raise SmokeError("Catalog returned no items.")
    for item in items:
        if wanted_id and str(item.get(id_key) or item.get("id") or "") == wanted_id:
            return item
        if name_contains and name_contains in str(item.get("name") or item.get("skillName") or ""):
            return item
    if wanted_id or name_contains:
        raise SmokeError(f"No catalog item matched id={wanted_id!r} name_contains={name_contains!r}")
    return items[0]


def skill_space_flow(client: StudioClient, log: StepLogger, config: dict[str, Any]) -> dict[str, Any]:
    skill_cfg = deep_get(config, "skill_space", {}) or {}
    region = str(skill_cfg.get("region") or "all")
    project = str(skill_cfg.get("project") or "")
    params = f"region={urllib.parse.quote(region, safe='')}&page_size={int(skill_cfg.get('page_size') or 50)}"
    if project:
        params += f"&project={urllib.parse.quote(project, safe='')}"
    log.step("Open Skill Space picker", "GET /web/skill-spaces")
    spaces_payload = client.json_request("GET", f"/web/skill-spaces?{params}")
    spaces = spaces_payload.get("items") if isinstance(spaces_payload, dict) else None
    if not isinstance(spaces, list):
        raise SmokeError(f"Invalid skill spaces payload: {spaces_payload}")
    space = choose_item(
        [item for item in spaces if isinstance(item, dict)],
        id_key="id",
        wanted_id=str(skill_cfg.get("space_id") or ""),
        name_contains=str(skill_cfg.get("space_name_contains") or ""),
    )
    skill_region = str(space.get("region") or (region if region != "all" else "cn-beijing"))
    log.step("Open skills in selected Skill Space", "GET /web/skill-spaces/{spaceId}/skills")
    skills_payload = client.json_request(
        "GET",
        f"/web/skill-spaces/{urllib.parse.quote(str(space['id']), safe='')}/skills"
        f"?region={urllib.parse.quote(skill_region, safe='')}&page_size=100",
    )
    skills = skills_payload.get("items") if isinstance(skills_payload, dict) else None
    if not isinstance(skills, list):
        raise SmokeError(f"Invalid skills payload: {skills_payload}")
    skill = choose_item(
        [item for item in skills if isinstance(item, dict)],
        id_key="skillId",
        wanted_id=str(skill_cfg.get("skill_id") or ""),
        name_contains=str(skill_cfg.get("skill_name_contains") or ""),
    )
    detail = None
    if truthy(skill_cfg.get("fetch_detail"), default=True):
        log.step("Open Skill detail", "GET /web/skill-spaces/{spaceId}/skills/{skillId}")
        version = str(skill_cfg.get("version") or skill.get("version") or "")
        q = f"region={urllib.parse.quote(skill_region, safe='')}"
        if version:
            q += f"&version={urllib.parse.quote(version, safe='')}"
        detail = client.json_request(
            "GET",
            f"/web/skill-spaces/{urllib.parse.quote(str(space['id']), safe='')}/skills/"
            f"{urllib.parse.quote(str(skill['skillId']), safe='')}?{q}",
        )
    return {"space": space, "skill": skill, "detail": detail}


def a2a_flow(client: StudioClient, log: StepLogger, config: dict[str, Any]) -> dict[str, Any]:
    a2a_cfg = deep_get(config, "a2a", {}) or {}
    region = str(a2a_cfg.get("region") or "cn-beijing")
    project = str(a2a_cfg.get("project") or "default")
    log.step("Open AgentKit A2A Space picker", "GET /web/a2a-spaces")
    payload = client.json_request(
        "GET",
        f"/web/a2a-spaces?region={urllib.parse.quote(region, safe='')}"
        f"&project={urllib.parse.quote(project, safe='')}&page_size={int(a2a_cfg.get('page_size') or 100)}",
    )
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise SmokeError(f"Invalid A2A spaces payload: {payload}")
    space = choose_item(
        [item for item in items if isinstance(item, dict)],
        id_key="id",
        wanted_id=str(a2a_cfg.get("space_id") or ""),
        name_contains=str(a2a_cfg.get("space_name_contains") or ""),
    )
    return {"space": space}


def selected_skill_from_catalog(selection: dict[str, Any]) -> dict[str, Any]:
    space = selection["space"]
    skill = selection["skill"]
    return {
        "source": "skillspace",
        "name": str(skill.get("skillName") or "skillspace_skill"),
        "folder": str(skill.get("skillName") or "skillspace_skill"),
        "description": str(skill.get("skillDescription") or ""),
        "skillSpaceId": str(space.get("id") or ""),
        "skillSpaceName": str(space.get("name") or ""),
        "skillSpaceRegion": str(space.get("region") or "cn-beijing"),
        "skillId": str(skill.get("skillId") or ""),
        "version": str(skill.get("version") or ""),
    }


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    if dry_run:
        return dry_summary(
            "catalog skill/a2a",
            {"skill_space": deep_get(config, "skill_space", {}), "a2a": deep_get(config, "a2a", {})},
        )
    log = StepLogger()
    client = StudioClient(config)
    verify_studio_ready(client, log)
    skill_selection = skill_space_flow(client, log, config) if truthy(deep_get(config, "skill_space.enabled"), default=True) else None
    a2a_selection = a2a_flow(client, log, config) if truthy(deep_get(config, "a2a.enabled"), default=True) else None
    deployment = None
    if truthy(deep_get(config, "deploy_catalog_agent.enabled")):
        draft = build_basic_draft(config, "studio-e2e-catalog")
        if skill_selection is not None:
            draft["selectedSkills"] = [selected_skill_from_catalog(skill_selection)]
        if a2a_selection is not None:
            a2a = deep_get(config, "a2a", {}) or {}
            draft["a2aRegistry"] = {
                "enabled": True,
                "registrySpaceId": str(a2a.get("space_id") or a2a_selection["space"].get("id") or ""),
                "registryTopK": str(a2a.get("top_k") or "3"),
                "registryRegion": str(a2a.get("region") or "cn-beijing"),
                "registryEndpoint": str(a2a.get("endpoint") or "https://open.volcengineapi.com/"),
            }
        project = generate_project_for_winner(client, log, "catalog", draft)
        expected = []
        if skill_selection is not None:
            expected.append("SkillToolset")
        if a2a_selection is not None:
            expected.append("build_a2a_registry_tools")
        assert_generated_contains(project, expected, "catalog generated agent")
        result = deploy_connect_chat(
            client,
            log,
            config,
            project,
            chat=truthy(deep_get(config, "chat.enabled"), default=True),
        )
        deployment = {"agentName": draft["name"], "deployment": result["final"], "chat": result["chat"]}
    return {
        "success": True,
        "skillSpace": skill_selection,
        "a2a": a2a_selection,
        "deployment": deployment,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run_workflow(load_config(Path(args.config).expanduser().resolve()), dry_run=args.dry_run)
    print("\n=== Summary ===")
    print_json("result", result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
