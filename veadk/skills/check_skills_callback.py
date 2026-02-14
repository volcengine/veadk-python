# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib
from pathlib import Path
from typing import Optional, Dict, List
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from veadk.skills.skill import Skill
from veadk.skills.utils import load_skill_from_directory, load_skills_from_cloud
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# Cache for storing skill states to detect changes
# Key format: "local:{path}" or "cloud:{skill_space_id}:{skill_name}"
skill_cache: Dict[str, str] = {}


def get_local_skill_hash(skill_directory: Path) -> str:
    """Calculate hash value for local skill directory to detect changes"""
    skill_readme = skill_directory / "SKILL.md"
    if not skill_readme.exists():
        return ""

    content = skill_readme.read_text(encoding="utf-8")
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def get_cloud_skill_hash(skill: Skill) -> str:
    """Calculate hash value for cloud skill based on name and description

    Args:
        skill: Skill object

    Returns:
        MD5 hash of skill name and description
    """
    content = f"{skill.name}|{skill.description}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def detect_skill_changes(
    current_skills_dict: Dict[str, Skill], reloaded_skills_dict: Dict[str, Skill]
) -> tuple[List[Skill], List[Skill], List[str]]:
    """Detect new, modified, and deleted skills by comparing current and reloaded skills

    Args:
        current_skills_dict: Current skills dictionary from agent
        reloaded_skills_dict: Newly reloaded skills dictionary

    Returns:
        Tuple of (new_skills, modified_skills, deleted_skill_names)
    """
    global skill_cache

    new_skills = []
    modified_skills = []
    deleted_skill_names = []

    # Check for new and modified skills
    for skill_name, reloaded_skill in reloaded_skills_dict.items():
        if skill_name not in current_skills_dict:
            # New skill detected
            new_skills.append(reloaded_skill)
            logger.info(f"Detected new skill: {skill_name}")

            # Initialize cache for new skill
            if reloaded_skill.skill_space_id:
                # Cloud skill - use name and description hash
                cache_key = f"cloud:{reloaded_skill.skill_space_id}:{skill_name}"
                skill_cache[cache_key] = get_cloud_skill_hash(reloaded_skill)
            else:
                # Local skill - use SKILL.md file hash
                cache_key = f"local:{reloaded_skill.path}"
                skill_cache[cache_key] = get_local_skill_hash(Path(reloaded_skill.path))
        else:
            # Existing skill - check if modified
            current_skill = current_skills_dict[skill_name]

            # Determine if skill is modified based on source type
            is_modified = False

            if reloaded_skill.skill_space_id:
                # Cloud skill - check using name and description
                cache_key = f"cloud:{reloaded_skill.skill_space_id}:{skill_name}"
                current_hash = get_cloud_skill_hash(reloaded_skill)
                previous_hash = skill_cache.get(cache_key, "")

                if previous_hash == "":
                    # First time seeing this skill, initialize cache but don't mark as modified
                    skill_cache[cache_key] = current_hash
                    logger.debug(f"Initialized cache for cloud skill: {skill_name}")
                elif current_hash != previous_hash:
                    # Hash changed, skill is modified
                    is_modified = True
                    skill_cache[cache_key] = current_hash
            else:
                # Local skill - check using file hash
                cache_key = f"local:{reloaded_skill.path}"
                current_hash = get_local_skill_hash(Path(reloaded_skill.path))
                previous_hash = skill_cache.get(cache_key, "")

                if previous_hash == "":
                    # First time seeing this skill, initialize cache but don't mark as modified
                    skill_cache[cache_key] = current_hash
                    logger.debug(f"Initialized cache for local skill: {skill_name}")
                elif current_hash != previous_hash:
                    # Hash changed, skill is modified
                    is_modified = True
                    skill_cache[cache_key] = current_hash

            if is_modified:
                modified_skills.append(reloaded_skill)
                logger.info(f"Detected modified skill: {skill_name}")

    # Check for deleted skills
    for skill_name in current_skills_dict.keys():
        if skill_name not in reloaded_skills_dict:
            deleted_skill_names.append(skill_name)
            logger.info(f"Detected deleted skill: {skill_name}")

            # Remove from cache
            current_skill = current_skills_dict[skill_name]
            if current_skill.skill_space_id:
                cache_key = f"cloud:{current_skill.skill_space_id}:{skill_name}"
            else:
                cache_key = f"local:{current_skill.path}"
            skill_cache.pop(cache_key, None)

    return new_skills, modified_skills, deleted_skill_names


def reload_skills_from_config(skills_config: List[str]) -> Dict[str, Skill]:
    """Reload all skills from configuration (both local and cloud)

    Args:
        skills_config: List of skill paths/IDs from agent configuration

    Returns:
        Dictionary mapping skill names to Skill objects
    """
    all_skills: Dict[str, Skill] = {}

    for item in skills_config:
        if not item or str(item).strip() == "":
            continue

        path = Path(item)

        # Check if it's a local directory
        if path.exists() and path.is_dir():
            logger.debug(f"Reloading skills from local directory: {path}")
            try:
                for skill_dir in path.iterdir():
                    if skill_dir.is_dir():
                        skill = load_skill_from_directory(skill_dir)
                        all_skills[skill.name] = skill
            except Exception as e:
                logger.error(
                    f"Failed to reload skills from local directory {path}: {e}"
                )
        else:
            # Treat as cloud skill space ID
            logger.debug(f"Reloading skills from cloud space: {item}")
            try:
                cloud_skills = load_skills_from_cloud(item)
                for skill in cloud_skills:
                    all_skills[skill.name] = skill
            except Exception as e:
                logger.error(f"Failed to reload skills from cloud space {item}: {e}")

    return all_skills


def rebuild_instruction_with_skills(
    current_instruction: str, skills_dict: Dict[str, Skill]
) -> str:
    """Rebuild instruction with updated skill list

    Args:
        current_instruction: Current agent instruction
        skills_dict: All current skills

    Returns:
        Updated instruction string
    """
    new_instruction_parts = []

    # Find the skills section start
    skills_section_start = current_instruction.find("You have the following skills:")

    if skills_section_start == -1:
        # No existing skills section, append new one
        new_instruction_parts.append(current_instruction)
        new_instruction_parts.append("\nYou have the following skills:\n")
    else:
        # Keep content before skills section
        new_instruction_parts.append(current_instruction[:skills_section_start])
        new_instruction_parts.append("You have the following skills:\n")

    # Add all current skills
    for skill in skills_dict.values():
        new_instruction_parts.append(
            f"- name: {skill.name}\n- description: {skill.description}\n\n"
        )

    # Determine the tool instruction based on skills_mode from agent
    if "skills_tool" in current_instruction:
        tool_instruction = (
            "You can use the skills by calling the `skills_tool` tool.\n\n"
        )
    elif "execute_skills" in current_instruction:
        tool_instruction = (
            "You can use the skills by calling the `execute_skills` tool.\n\n"
        )
    else:
        tool_instruction = "You can use the skills by calling the appropriate tool.\n\n"

    new_instruction_parts.append(tool_instruction)

    return "".join(new_instruction_parts)


def update_skills_toolset(
    callback_context: CallbackContext, updated_skills_dict: Dict[str, Skill]
) -> None:
    """Remove old SkillsToolset and add new one with updated skills

    Args:
        callback_context: Callback context containing agent information
        updated_skills_dict: Updated skills dictionary
    """
    try:
        from veadk.tools.skills_tools.skills_toolset import SkillsToolset

        agent = callback_context._invocation_context.agent

        # Find and remove existing SkillsToolset
        tools_to_remove = []
        for i, tool in enumerate(agent.tools):
            if isinstance(tool, SkillsToolset):
                tools_to_remove.append(i)
                logger.debug(f"Found SkillsToolset at index {i}, will remove it")

        # Remove in reverse order to avoid index shifting issues
        for i in reversed(tools_to_remove):
            agent.tools.pop(i)
            logger.info("Removed old SkillsToolset from agent tools")

        # Get skills_mode from agent
        skills_mode = getattr(agent, "skills_mode", "local")

        # Add new SkillsToolset with updated skills
        new_toolset = SkillsToolset(updated_skills_dict, skills_mode)
        agent.tools.append(new_toolset)
        logger.info(f"Added new SkillsToolset with {len(updated_skills_dict)} skills")

    except Exception as e:
        logger.error(f"Failed to update SkillsToolset: {e}", exc_info=True)


def check_skills(callback_context: CallbackContext) -> Optional[types.Content]:
    """Check for skill changes and update agent instruction and toolset dynamically

    This callback checks both local directory skills and cloud space skills for changes,
    including new skills, modified skills, and deleted skills. When changes are detected,
    it updates the agent's instruction and reloads the SkillsToolset.

    The detection process:
    1. Reload all skills from the original configuration
    2. Compare with current skills_dict to detect:
       - New skills: present in reloaded but not in current
       - Modified skills: present in both but content changed (via hash comparison)
         * Local skills: compare SKILL.md file hash
         * Cloud skills: compare name and description hash
       - Deleted skills: present in current but not in reloaded
    3. Update agent.skills_dict with the reloaded skills
    4. Rebuild instruction with updated skill list
    5. Replace SkillsToolset with new instance using updated skills

    Note: On first run when cache is empty, skills are initialized in cache but not
    marked as modified to avoid false positives.

    Args:
        callback_context: Callback context containing agent information

    Returns:
        None (updates agent instruction, skills_dict and tools in-place)
    """
    global skill_cache

    try:
        agent = callback_context._invocation_context.agent

        # Get current skills_dict from agent
        if not hasattr(agent, "skills_dict"):
            logger.debug("Agent has no skills_dict attribute, skip checking")
            return None

        current_skills_dict = agent.skills_dict

        # Get skills configuration from agent
        if not hasattr(agent, "skills") or not agent.skills:
            logger.debug("Agent has no skills configuration, skip checking")
            return None

        # Reload skills from original configuration
        reloaded_skills_dict = reload_skills_from_config(agent.skills)

        # If both are empty, skip
        if not current_skills_dict and not reloaded_skills_dict:
            logger.debug("No skills found in both current and reloaded, skip checking")
            return None

        # Detect changes
        new_skills, modified_skills, deleted_skill_names = detect_skill_changes(
            current_skills_dict, reloaded_skills_dict
        )

        # If no changes detected, return early
        if not new_skills and not modified_skills and not deleted_skill_names:
            logger.debug("No skill changes detected")
            return None

        # Log changes
        if new_skills:
            logger.info(f"New skills: {[s.name for s in new_skills]}")
        if modified_skills:
            logger.info(f"Modified skills: {[s.name for s in modified_skills]}")
        if deleted_skill_names:
            logger.info(f"Deleted skills: {deleted_skill_names}")

        # Update agent.skills_dict with reloaded skills
        agent.skills_dict = reloaded_skills_dict
        agent._skills_with_checklist = reloaded_skills_dict
        logger.info(
            f"Updated agent.skills_dict with {len(reloaded_skills_dict)} skills"
        )

        # Rebuild instruction with updated skills
        current_instruction = agent.instruction
        new_instruction = rebuild_instruction_with_skills(
            current_instruction, reloaded_skills_dict
        )

        # Update agent instruction
        agent.instruction = new_instruction
        logger.info("Agent instruction updated with skill changes")

        # Update SkillsToolset with new skills_dict
        update_skills_toolset(callback_context, reloaded_skills_dict)

    except Exception as e:
        logger.error(f"Error checking skills: {e}", exc_info=True)

    return None
