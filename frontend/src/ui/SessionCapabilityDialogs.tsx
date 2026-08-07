import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  searchSessionPublicSkills,
  type AddSessionCapability,
  type SessionPublicSkill,
} from "../adk/client";
import {
  listSkillsInSpace,
  listSkillSpaces,
  type SkillSpaceRef,
  type SkillSpaceSkill,
} from "../create/skills/skillspace";
import { BUILTIN_TOOLS } from "../create/veadkCatalog";
import { ToolCapabilityIcon } from "./CapabilityIcons";

const SESSION_TOOL_LABELS: Record<string, string> = {
  coding: "智能编程",
  get_city_weather: "城市天气查询",
  get_location_weather: "位置天气查询",
  web_fetch: "网页内容获取",
};

export function sessionToolLabel(name: string): string {
  const catalogTool = BUILTIN_TOOLS.find(
    (tool) => tool.id === name || tool.toolNames.includes(name),
  );
  return SESSION_TOOL_LABELS[name] ?? catalogTool?.label ?? name;
}

function sessionToolDescription(name: string): string {
  const catalogTool = BUILTIN_TOOLS.find(
    (tool) => tool.id === name || tool.toolNames.includes(name),
  );
  const description = catalogTool?.desc ?? "由 VeADK 提供的内置工具";
  return description.replace(/[。.]+$/, "");
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m7 7 10 10M17 7 7 17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="10.8" cy="10.8" r="5.8" stroke="currentColor" strokeWidth="1.7" />
      <path d="m15.2 15.2 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 5.5v13M5.5 12h13" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function DialogShell({
  title,
  description,
  icon,
  wide = false,
  onClose,
  children,
}: {
  title: string;
  description: string;
  icon?: ReactNode;
  wide?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const titleId = useRef(`session-capability-${Math.random().toString(36).slice(2)}`);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return createPortal(
    <div className="session-capability-dialog-layer">
      <button
        type="button"
        className="session-capability-dialog-scrim"
        aria-label="关闭弹窗"
        onClick={onClose}
      />
      <section
        className={`session-capability-dialog${wide ? " is-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId.current}
      >
        <header className={`session-capability-dialog-head${icon ? "" : " is-iconless"}`}>
          {icon && <span className="session-capability-dialog-mark">{icon}</span>}
          <div>
            <h2 id={titleId.current}>{title}</h2>
            <p>{description}</p>
          </div>
          <button
            type="button"
            className="session-capability-dialog-close"
            aria-label={`关闭${title}`}
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </header>
        {children}
      </section>
    </div>,
    document.body,
  );
}

function SearchField({
  value,
  placeholder,
  label,
  onChange,
  autoFocus = false,
}: {
  value: string;
  placeholder: string;
  label: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
}) {
  return (
    <label className="session-capability-search">
      <SearchIcon />
      <input
        value={value}
        aria-label={label}
        placeholder={placeholder}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export function ToolCapabilityDialog({
  agentName,
  tools,
  selectedNames,
  mutating,
  onAdd,
  onClose,
}: {
  agentName: string;
  tools: string[];
  selectedNames: string[];
  mutating: boolean;
  onAdd: (capability: AddSessionCapability) => Promise<boolean>;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState("");
  const selected = useMemo(() => new Set(selectedNames), [selectedNames]);
  const filteredTools = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return tools.filter((name) => {
      if (!normalized) return true;
      return `${sessionToolLabel(name)} ${name} ${sessionToolDescription(name)}`
        .toLowerCase()
        .includes(normalized);
    });
  }, [query, tools]);

  const addTool = async (name: string) => {
    setPending(name);
    const added = await onAdd({ kind: "tool", name });
    setPending("");
    if (added) onClose();
  };

  return (
    <DialogShell
      title="添加内置工具"
      description={`添加后仅对 ${agentName} 的当前会话生效`}
      icon={<ToolCapabilityIcon />}
      onClose={onClose}
    >
      <div className="session-tool-dialog-body">
        <SearchField
          value={query}
          label="搜索内置工具"
          placeholder="搜索中文名称或工具标识"
          onChange={setQuery}
          autoFocus
        />
        <div className="session-tool-picker" role="list" aria-label="可用内置工具">
          {filteredTools.length === 0 ? (
            <div className="session-capability-empty">没有匹配的内置工具</div>
          ) : (
            filteredTools.map((name) => {
              const added = selected.has(name);
              const isPending = pending === name;
              return (
                <article key={name} className="session-tool-option" role="listitem">
                  <span className="session-tool-option-icon"><ToolCapabilityIcon /></span>
                  <span className="session-tool-option-copy">
                    <strong>{sessionToolLabel(name)}</strong>
                    <code>{name}</code>
                    <span>{sessionToolDescription(name)}</span>
                  </span>
                  <button
                    type="button"
                    disabled={added || mutating || Boolean(pending)}
                    onClick={() => void addTool(name)}
                  >
                    {added ? "已添加" : isPending ? "添加中…" : "添加"}
                  </button>
                </article>
              );
            })
          )}
        </div>
      </div>
    </DialogShell>
  );
}

export function SkillCapabilityDialog({
  appName,
  agentName,
  selectedNames,
  mutating,
  onAdd,
  onClose,
}: {
  appName: string;
  agentName: string;
  selectedNames: string[];
  mutating: boolean;
  onAdd: (capability: AddSessionCapability) => Promise<boolean>;
  onClose: () => void;
}) {
  const [sourceTab, setSourceTab] = useState<"public" | "agentkit">("public");
  const [publicQuery, setPublicQuery] = useState("");
  const [publicSkills, setPublicSkills] = useState<SessionPublicSkill[]>([]);
  const [publicTotal, setPublicTotal] = useState(0);
  const [publicLoading, setPublicLoading] = useState(true);
  const [publicError, setPublicError] = useState("");
  const [spaces, setSpaces] = useState<SkillSpaceRef[]>([]);
  const [selectedSpace, setSelectedSpace] = useState<SkillSpaceRef | null>(null);
  const [skills, setSkills] = useState<SkillSpaceSkill[]>([]);
  const [spaceQuery, setSpaceQuery] = useState("");
  const [skillQuery, setSkillQuery] = useState("");
  const [spacesLoading, setSpacesLoading] = useState(true);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [spacesError, setSpacesError] = useState("");
  const [skillsError, setSkillsError] = useState("");
  const [spacesReloadKey, setSpacesReloadKey] = useState(0);
  const [pending, setPending] = useState("");
  const selected = useMemo(() => new Set(selectedNames), [selectedNames]);

  useEffect(() => {
    if (sourceTab !== "public") return;
    let active = true;
    const timer = window.setTimeout(() => {
      setPublicLoading(true);
      setPublicError("");
      void searchSessionPublicSkills(appName, publicQuery.trim())
        .then((result) => {
          if (!active) return;
          setPublicSkills(result.items);
          setPublicTotal(result.totalCount);
        })
        .catch((reason: unknown) => {
          if (!active) return;
          setPublicSkills([]);
          setPublicTotal(0);
          setPublicError(reason instanceof Error ? reason.message : "搜索 Skill Hub 失败");
        })
        .finally(() => {
          if (active) setPublicLoading(false);
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [appName, publicQuery, sourceTab]);

  useEffect(() => {
    if (sourceTab !== "agentkit") return;
    let active = true;
    setSpacesLoading(true);
    setSpacesError("");
    void listSkillSpaces()
      .then((items) => {
        if (!active) return;
        setSpaces(items);
        setSelectedSpace(items[0] ?? null);
      })
      .catch((reason: unknown) => {
        if (active) setSpacesError(reason instanceof Error ? reason.message : "读取 Skill Space 失败");
      })
      .finally(() => {
        if (active) setSpacesLoading(false);
      });
    return () => { active = false; };
  }, [sourceTab, spacesReloadKey]);

  useEffect(() => {
    if (sourceTab !== "agentkit") return;
    if (!selectedSpace) {
      setSkills([]);
      return;
    }
    let active = true;
    setSkillsLoading(true);
    setSkillsError("");
    void listSkillsInSpace(selectedSpace.id, selectedSpace.region)
      .then((items) => {
        if (active) setSkills(items);
      })
      .catch((reason: unknown) => {
        if (active) setSkillsError(reason instanceof Error ? reason.message : "读取技能失败");
      })
      .finally(() => {
        if (active) setSkillsLoading(false);
      });
    return () => { active = false; };
  }, [selectedSpace, sourceTab]);

  const filteredSpaces = useMemo(() => {
    const normalized = spaceQuery.trim().toLowerCase();
    if (!normalized) return spaces;
    return spaces.filter((space) =>
      `${space.name} ${space.id} ${space.description}`.toLowerCase().includes(normalized),
    );
  }, [spaceQuery, spaces]);

  const filteredSkills = useMemo(() => {
    const normalized = skillQuery.trim().toLowerCase();
    if (!normalized) return skills;
    return skills.filter((skill) =>
      `${skill.skillName} ${skill.skillDescription}`.toLowerCase().includes(normalized),
    );
  }, [skillQuery, skills]);

  const addSkill = async (skill: SkillSpaceSkill) => {
    if (!selectedSpace) return;
    setPending(skill.skillId);
    const added = await onAdd({
      kind: "skill",
      name: skill.skillName,
      skillSourceId: selectedSpace.id,
      description: skill.skillDescription,
      version: skill.version,
    });
    setPending("");
    if (added) onClose();
  };

  const addPublicSkill = async (skill: SessionPublicSkill) => {
    setPending(skill.slug);
    const added = await onAdd({
      kind: "skill",
      name: skill.name,
      skillSourceId: `findskill:${skill.slug}`,
      description: skill.description,
      version: skill.version || skill.updatedAt,
    });
    setPending("");
    if (added) onClose();
  };

  return (
    <DialogShell
      title="添加技能"
      description={`从公域 Skill Hub 或 AgentKit Skill 中心添加到 ${agentName} 当前会话`}
      wide
      onClose={onClose}
    >
      <div className="session-skill-dialog-body">
        <div className="session-skill-source-tabs" role="tablist" aria-label="技能来源">
          <button
            type="button"
            role="tab"
            aria-selected={sourceTab === "public"}
            className={sourceTab === "public" ? "is-active" : ""}
            onClick={() => setSourceTab("public")}
          >
            Skill Hub
            <span>公域</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={sourceTab === "agentkit"}
            className={sourceTab === "agentkit" ? "is-active" : ""}
            onClick={() => setSourceTab("agentkit")}
          >
            AgentKit Skill 中心
          </button>
        </div>

        {sourceTab === "public" ? (
          <section className="session-public-skill-browser" aria-label="Skill Hub 公域技能">
            <div className="session-public-skill-head">
              <SearchField
                value={publicQuery}
                label="搜索 Skill Hub"
                placeholder="搜索技能名称、用途或关键词"
                onChange={setPublicQuery}
                autoFocus
              />
              <span>{publicTotal.toLocaleString()} 个公域技能</span>
            </div>
            <div className="session-public-skill-list">
              {publicError ? (
                <div className="session-capability-error" role="alert">{publicError}</div>
              ) : publicLoading ? (
                <div className="session-capability-loading">正在搜索 Skill Hub…</div>
              ) : publicSkills.length === 0 ? (
                <div className="session-capability-empty">没有匹配的公域技能</div>
              ) : (
                publicSkills.map((skill) => {
                  const added = selected.has(skill.name);
                  const isPending = pending === skill.slug;
                  return (
                    <article key={skill.slug} className="session-skill-option session-public-skill-option">
                      <span className="session-skill-option-copy">
                        <strong>{skill.name}</strong>
                        <span>{skill.description || "暂无描述"}</span>
                        <small>
                          {skill.sourceRepo || skill.sourceType || "FindSkill"}
                          <span aria-hidden="true"> · </span>
                          {skill.downloadCount.toLocaleString()} 次下载
                          {skill.evaluationScore > 0 && (
                            <><span aria-hidden="true"> · </span>{skill.evaluationScore.toFixed(1)} 分</>
                          )}
                        </small>
                      </span>
                      <button
                        type="button"
                        disabled={added || mutating || Boolean(pending)}
                        onClick={() => void addPublicSkill(skill)}
                      >
                        {added ? "已添加" : isPending ? "添加中…" : <><PlusIcon />添加</>}
                      </button>
                    </article>
                  );
                })
              )}
            </div>
          </section>
        ) : (
          <div className="session-skill-browser">
            <section className="session-skill-spaces" aria-label="Skill Space 列表">
              <div className="session-skill-pane-head">
                <div>
                  <strong>Skill Space</strong>
                  <span>{spaces.length}</span>
                </div>
                <SearchField
                  value={spaceQuery}
                  label="搜索 Skill Space"
                  placeholder="搜索空间"
                  onChange={setSpaceQuery}
                  autoFocus
                />
              </div>
              <div className="session-skill-pane-list">
                {spacesLoading ? (
                  <div className="session-capability-loading">正在读取 Skill Space…</div>
                ) : spacesError ? (
                  <div className="session-capability-error" role="alert">
                    <span>{spacesError}</span>
                    <button type="button" onClick={() => setSpacesReloadKey(k => k + 1)}>重试</button>
                  </div>
                ) : filteredSpaces.length === 0 ? (
                  <div className="session-capability-empty">没有匹配的 Skill Space</div>
                ) : (
                  filteredSpaces.map((space) => (
                    <button
                      type="button"
                      key={`${space.projectName ?? "default"}:${space.id}`}
                      className={`session-skill-space${selectedSpace?.id === space.id ? " is-active" : ""}`}
                      onClick={() => {
                        setSelectedSpace(space);
                        setSkillQuery("");
                      }}
                    >
                      <span>
                        <strong>{space.name || space.id}</strong>
                        <small>{space.description || space.id}</small>
                        <em>{space.skillCount ?? 0} 个技能</em>
                      </span>
                    </button>
                  ))
                )}
              </div>
            </section>

            <section className="session-skill-results" aria-label="AgentKit Skill 列表">
              <div className="session-skill-pane-head">
                <div>
                  <strong title={selectedSpace?.name}>{selectedSpace?.name || "选择 Skill Space"}</strong>
                  <span>{skills.length}</span>
                </div>
                <SearchField
                  value={skillQuery}
                  label="搜索 AgentKit 技能"
                  placeholder="搜索技能名称或描述"
                  onChange={setSkillQuery}
                />
              </div>
              <div className="session-skill-pane-list">
                {skillsError ? (
                  <div className="session-capability-error" role="alert">{skillsError}</div>
                ) : !selectedSpace ? (
                  <div className="session-capability-empty">选择一个 Skill Space 查看技能</div>
                ) : skillsLoading ? (
                  <div className="session-capability-loading">正在读取技能…</div>
                ) : filteredSkills.length === 0 ? (
                  <div className="session-capability-empty">没有匹配的技能</div>
                ) : (
                  filteredSkills.map((skill) => {
                    const added = selected.has(skill.skillName);
                    const isPending = pending === skill.skillId;
                    return (
                      <article key={`${skill.skillId}:${skill.version}`} className="session-skill-option">
                        <span className="session-skill-option-copy">
                          <strong>{skill.skillName}</strong>
                          <span>{skill.skillDescription || "暂无描述"}</span>
                          <small>版本 {skill.version || "—"}</small>
                        </span>
                        <button
                          type="button"
                          disabled={added || mutating || Boolean(pending)}
                          onClick={() => void addSkill(skill)}
                        >
                          {added ? "已添加" : isPending ? "添加中…" : <><PlusIcon />添加</>}
                        </button>
                      </article>
                    );
                  })
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </DialogShell>
  );
}
