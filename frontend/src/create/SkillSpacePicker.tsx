// Volcengine AgentKit SkillSpace picker. Lists account-scoped SkillSpaces via
// the server-side /web/skill-spaces* routes (which sign with the SERVER's AK/SK
// so the browser never sees credentials), lists skills within a chosen space,
// and lets the user toggle them into the draft. SKILL.md content is fetched at
// project-generation time (downloadSkillSpaceSkill) so we don't bloat YAML
// exports with markdown.

import { useEffect, useState } from "react";
import { Check, Cloud, Info, Loader2, Plus } from "lucide-react";
import {
  listSkillSpaces,
  listSkillsInSpace,
  toHit,
  type SkillSpaceRef,
  type SkillSpaceSkill,
} from "./skills/skillspace";
import type { SelectedSkill, SkillHit } from "./skills/types";

export function SkillSpacePicker({
  selected,
  onChange,
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
}) {
  const [spaces, setSpaces] = useState<SkillSpaceRef[]>([]);
  const [skills, setSkills] = useState<SkillSpaceSkill[]>([]);
  const [spaceId, setSpaceId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const sp = await listSkillSpaces();
        if (!cancelled) {
          setSpaces(sp);
          if (sp.length > 0) setSpaceId(sp[0].id);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!spaceId) {
      setSkills([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingSkills(true);
      setError(null);
      try {
        const sk = await listSkillsInSpace(spaceId);
        if (!cancelled) setSkills(sk);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        if (!cancelled) setLoadingSkills(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [spaceId]);

  const selectedSpace = spaces.find((s) => s.id === spaceId);

  const isSelected = (skillId: string, ver: string) =>
    selected.some(
      (s) =>
        s.source === "skillspace" && s.skillId === skillId && (s.version || "") === ver,
    );

  const toggle = (skill: SkillSpaceSkill) => {
    if (!selectedSpace) return;
    if (isSelected(skill.skillId, skill.version)) {
      onChange(
        selected.filter(
          (s) =>
            !(
              s.source === "skillspace" &&
              s.skillId === skill.skillId &&
              (s.version || "") === skill.version
            ),
        ),
      );
    } else {
      const hit: SkillHit = toHit(selectedSpace, skill);
      onChange([
        ...selected,
        {
          source: "skillspace",
          folder: hit.folder || skill.skillName,
          name: hit.name,
          description: hit.description,
          skillSpaceId: hit.skillSpaceId,
          skillSpaceName: hit.skillSpaceName,
          skillId: hit.skillId,
          version: hit.version,
        },
      ]);
    }
  };

  return (
    <div className="cw-skillspace">
      {loading ? (
        <p className="cw-empty-line">
          <Loader2 className="cw-i cw-spin" /> 正在加载 SkillSpace 列表…
        </p>
      ) : error ? (
        <div className="cw-banner">
          <Info className="cw-i" />
          <span>{error}</span>
        </div>
      ) : spaces.length === 0 ? (
        <p className="cw-empty-line">此账号下没有 SkillSpace。</p>
      ) : (
        <>
          <select
            className="cw-input cw-skillspace-select"
            value={spaceId}
            onChange={(e) => setSpaceId(e.target.value)}
            aria-label="选择 SkillSpace"
          >
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name || s.id}
                {s.description ? ` — ${s.description}` : ""}
              </option>
            ))}
          </select>

          {loadingSkills ? (
            <p className="cw-empty-line">
              <Loader2 className="cw-i cw-spin" /> 正在加载技能列表…
            </p>
          ) : skills.length === 0 ? (
            <p className="cw-empty-line">此 SkillSpace 暂无技能。</p>
          ) : (
            <div className="cw-skill-results">
              {skills.map((sk) => {
                const on = isSelected(sk.skillId, sk.version);
                return (
                  <button
                    key={`${sk.skillId}/${sk.version}`}
                    type="button"
                    className={`cw-skill-result ${on ? "is-on" : ""}`}
                    onClick={() => toggle(sk)}
                    aria-pressed={on}
                  >
                    <span className="cw-skill-result-icon" aria-hidden>
                      {on ? (
                        <Check className="cw-i cw-i-sm" />
                      ) : (
                        <Plus className="cw-i cw-i-sm" />
                      )}
                    </span>
                    <span className="cw-skill-result-meta">
                      <span className="cw-skill-result-name">
                        {sk.skillName}
                        {sk.version && (
                          <span className="cw-skill-result-version">
                            {" "}
                            v{sk.version}
                          </span>
                        )}
                      </span>
                      {sk.skillDescription && (
                        <span className="cw-skill-result-desc">
                          {sk.skillDescription}
                        </span>
                      )}
                      <span className="cw-skill-result-repo">
                        <Cloud className="cw-i cw-i-sm" /> {selectedSpace?.name || spaceId}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
