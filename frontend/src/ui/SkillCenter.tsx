import { useEffect, useRef, useState } from "react";
import {
  getSkillDetail,
  listSkillSpacesPage,
  listSkillsInSpacePage,
  type SkillDetail,
  type SkillSpaceRef,
  type SkillSpaceSkill,
} from "../create/skills/skillspace";
import { Markdown } from "./Markdown";

const SPACE_PAGE_SIZE = 6;
const SKILL_PAGE_SIZE = 7;

type SkillRegion = "cn-beijing" | "cn-shanghai";

const STATUS_LABELS: Record<string, string> = {
  active: "可用",
  available: "可用",
  creating: "创建中",
  disabled: "已停用",
  enabled: "已启用",
  failed: "异常",
  inactive: "未启用",
  pending: "等待中",
  published: "已发布",
  ready: "就绪",
  released: "已发布",
  running: "运行中",
  success: "正常",
  unavailable: "不可用",
  unreleased: "未发布",
  updating: "更新中",
};

function statusLabel(status?: string): string {
  return STATUS_LABELS[(status || "").trim().toLowerCase()] || "未知";
}

function statusTone(status?: string): string {
  const value = (status || "").toLowerCase();
  if (["active", "available", "enabled", "published", "ready", "released", "success"].includes(value)) {
    return "is-positive";
  }
  if (["creating", "pending", "running", "updating"].includes(value)) return "is-progress";
  if (["failed", "unavailable"].includes(value)) return "is-danger";
  return "is-muted";
}

function updatedAtLabel(value?: string): string {
  if (!value) return "";
  const trimmed = value.trim();
  const numeric = Number(trimmed);
  const date = /^\d+(?:\.\d+)?$/.test(trimmed)
    ? new Date(numeric < 1_000_000_000_000 ? numeric * 1000 : numeric)
    : new Date(trimmed);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function skillMarkdownBody(value: string): string {
  const normalized = value.replace(/\r\n/g, "\n");
  if (!normalized.startsWith("---\n")) return value;
  const closingDelimiter = normalized.indexOf("\n---\n", 4);
  return closingDelimiter >= 0
    ? normalized.slice(closingDelimiter + 5).trimStart()
    : value;
}

/** Hand-drawn Skill Space mark: two connected shelves for a skill collection. */
function SkillSpaceIcon({ className = "icon" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M5.25 7.5h5.25v5.25H5.25zM13.5 7.5h5.25v5.25H13.5zM9.38 15.75h5.24v3H9.38z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M7.88 12.75v1.5c0 .83.67 1.5 1.5 1.5h5.24c.83 0 1.5-.67 1.5-1.5v-1.5M12 4.75V7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="12" cy="4.75" r="1" fill="currentColor" />
    </svg>
  );
}

/** Hand-drawn Skill mark: a compact instruction card with an activation spark. */
function SkillIcon({ className = "icon" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M6.25 4.75h8.6l2.9 2.9v11.6h-11.5z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M14.75 4.9v3h2.85M8.9 11.1h4.2M8.9 14h5.7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="m17.85 13.85.42 1.13 1.13.42-1.13.42-.42 1.13-.42-1.13-1.13-.42 1.13-.42z" fill="currentColor" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="m7.5 7.5 9 9m0-9-9 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function ArrowIcon({ direction }: { direction: "left" | "right" }) {
  return (
    <svg className="icon" viewBox="0 0 20 20" fill="none" aria-hidden>
      <path
        d={direction === "left" ? "m11.7 5.5-4.2 4.5 4.2 4.5" : "m8.3 5.5 4.2 4.5-4.2 4.5"}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LoadingMark() {
  return <span className="skillcenter-loading-mark" aria-hidden />;
}

function Pager({
  page,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  return (
    <footer className="skillcenter-pager">
      <span>共 {total} 项</span>
      <div className="skillcenter-pager-actions">
        <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="上一页">
          <ArrowIcon direction="left" />
        </button>
        <span>{page} / {pageCount}</span>
        <button type="button" onClick={() => onPage(page + 1)} disabled={page >= pageCount} aria-label="下一页">
          <ArrowIcon direction="right" />
        </button>
      </div>
    </footer>
  );
}

function EmptyState({ children }: { children: string }) {
  return <div className="skillcenter-empty">{children}</div>;
}

function SkillDetailDialog({
  skill,
  space,
  region,
  detail,
  loading,
  error,
  onClose,
}: {
  skill: SkillSpaceSkill;
  space: SkillSpaceRef;
  region: SkillRegion;
  detail: SkillDetail | null;
  loading: boolean;
  error: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="skill-detail-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="skill-detail-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-detail-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="skill-detail-head">
          <div className="skill-detail-heading">
            <span className="skillcenter-symbol skillcenter-symbol--skill"><SkillIcon /></span>
            <div>
              <h2 id="skill-detail-title">{detail?.name || skill.skillName}</h2>
              <p>{detail?.description || skill.skillDescription || "暂无描述"}</p>
            </div>
          </div>
          <button type="button" className="skill-detail-close" onClick={onClose} aria-label="关闭技能详情">
            <CloseIcon />
          </button>
        </header>

        <dl className="skill-detail-meta">
          <div><dt>技能 ID</dt><dd title={skill.skillId}>{skill.skillId}</dd></div>
          <div><dt>版本</dt><dd>{detail?.version || skill.version || "—"}</dd></div>
          <div><dt>状态</dt><dd>{statusLabel(skill.skillStatus)}</dd></div>
          <div><dt>技能空间</dt><dd title={space.name}>{space.name}</dd></div>
          <div><dt>Project</dt><dd title={space.projectName || "default"}>{space.projectName || "default"}</dd></div>
          <div><dt>地域</dt><dd>{region === "cn-beijing" ? "北京" : "上海"}</dd></div>
        </dl>

        <div className="skill-detail-content">
          <div className="skill-detail-content-title">SKILL.md</div>
          {loading ? (
            <div className="skillcenter-loading"><LoadingMark />正在读取技能内容…</div>
          ) : error ? (
            <div className="skillcenter-error">{error}</div>
          ) : detail?.skillMd ? (
            <Markdown
              text={skillMarkdownBody(detail.skillMd)}
              className="skill-detail-markdown"
              allowRawHtml={false}
            />
          ) : (
            <EmptyState>该技能暂无 SKILL.md 内容</EmptyState>
          )}
        </div>
      </section>
    </div>
  );
}

/** Sidebar entry that opens the skill center view in the main panel. */
export function SkillCenterButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="new-chat" onClick={onClick} aria-label="技能中心" title="技能中心">
      <SkillSpaceIcon />
      <span className="sidebar-nav-label">技能中心</span>
    </button>
  );
}

/** Native AgentKit Skill space browser. */
export function SkillCenterView() {
  const [region, setRegion] = useState<SkillRegion>("cn-beijing");
  const [spaces, setSpaces] = useState<SkillSpaceRef[]>([]);
  const [spacePage, setSpacePage] = useState(1);
  const [spaceTotal, setSpaceTotal] = useState(0);
  const [spacesLoading, setSpacesLoading] = useState(false);
  const [spacesError, setSpacesError] = useState("");
  const [selectedSpace, setSelectedSpace] = useState<SkillSpaceRef | null>(null);
  const [skills, setSkills] = useState<SkillSpaceSkill[]>([]);
  const [skillPage, setSkillPage] = useState(1);
  const [skillTotal, setSkillTotal] = useState(0);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState("");
  const [detailSkill, setDetailSkill] = useState<SkillSpaceSkill | null>(null);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const detailRequest = useRef(0);

  useEffect(() => {
    let active = true;
    setSpacesLoading(true);
    setSpacesError("");
    void listSkillSpacesPage({ region, page: spacePage, pageSize: SPACE_PAGE_SIZE })
      .then((result) => {
        if (!active) return;
        const items = result.items || [];
        setSpaces(items);
        setSpaceTotal(result.totalCount || 0);
        setSelectedSpace((current) => items.find((space) => space.id === current?.id) || null);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSpaces([]);
        setSpaceTotal(0);
        setSelectedSpace(null);
        setSpacesError(error instanceof Error ? error.message : "读取技能空间失败，请稍后重试");
      })
      .finally(() => {
        if (active) setSpacesLoading(false);
      });
    return () => { active = false; };
  }, [region, spacePage]);

  useEffect(() => {
    if (!selectedSpace) {
      setSkills([]);
      setSkillTotal(0);
      return;
    }
    let active = true;
    setSkillsLoading(true);
    setSkillsError("");
    void listSkillsInSpacePage(selectedSpace.id, {
      region,
      page: skillPage,
      pageSize: SKILL_PAGE_SIZE,
      project: selectedSpace.projectName,
    })
      .then((result) => {
        if (!active) return;
        setSkills(result.items || []);
        setSkillTotal(result.totalCount || 0);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSkills([]);
        setSkillTotal(0);
        setSkillsError(error instanceof Error ? error.message : "读取技能失败，请稍后重试");
      })
      .finally(() => {
        if (active) setSkillsLoading(false);
      });
    return () => { active = false; };
  }, [region, selectedSpace, skillPage]);

  const changeRegion = (nextRegion: SkillRegion) => {
    if (nextRegion === region) return;
    closeDetail();
    setRegion(nextRegion);
    setSpacePage(1);
    setSkillPage(1);
    setSelectedSpace(null);
    setSkills([]);
  };

  const selectSpace = (space: SkillSpaceRef) => {
    closeDetail();
    setSelectedSpace(space);
    setSkillPage(1);
  };

  const closeDetail = () => {
    detailRequest.current += 1;
    setDetailSkill(null);
    setDetail(null);
    setDetailError("");
    setDetailLoading(false);
  };

  const openDetail = async (skill: SkillSpaceSkill) => {
    if (!selectedSpace) return;
    const request = detailRequest.current + 1;
    detailRequest.current = request;
    setDetailSkill(skill);
    setDetail(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const result = await getSkillDetail(
        selectedSpace.id,
        skill.skillId,
        skill.version,
        region,
        selectedSpace.projectName,
      );
      if (detailRequest.current === request) setDetail(result);
    } catch (error) {
      if (detailRequest.current === request) {
        setDetailError(error instanceof Error ? error.message : "读取技能详情失败，请稍后重试");
      }
    } finally {
      if (detailRequest.current === request) setDetailLoading(false);
    }
  };

  return (
    <section className="skillcenter">
      <div className="skillcenter-browser">
          <section className="skillcenter-panel" aria-label="技能空间列表">
            <header className="skillcenter-panel-head">
              <div>
                <h2>技能空间</h2>
                <span className="skillcenter-count-badge">{spaceTotal}</span>
              </div>
              <div className="skillcenter-regions" aria-label="地域">
                <button type="button" className={region === "cn-beijing" ? "active" : ""} onClick={() => changeRegion("cn-beijing")}>北京</button>
                <button type="button" className={region === "cn-shanghai" ? "active" : ""} onClick={() => changeRegion("cn-shanghai")}>上海</button>
              </div>
            </header>
            <div className="skillcenter-listwrap">
              {spacesLoading && <div className="skillcenter-loading skillcenter-loading--overlay"><LoadingMark />正在读取技能空间…</div>}
              {spacesError ? (
                <div className="skillcenter-error">{spacesError}</div>
              ) : spaces.length === 0 && !spacesLoading ? (
                <EmptyState>当前地域暂无可访问的技能空间</EmptyState>
              ) : (
                <div className="skillcenter-list">
                  {spaces.map((space) => (
                    <button
                      type="button"
                      key={`${space.projectName || "default"}:${space.id}`}
                      className={`skillcenter-space-item ${selectedSpace?.id === space.id ? "active" : ""}`}
                      onClick={() => selectSpace(space)}
                    >
                      <span className="skillcenter-item-body">
                        <span className="skillcenter-item-title" title={space.name}>{space.name}</span>
                        <span className="skillcenter-item-description">{space.description || "暂无描述"}</span>
                        <span className="skillcenter-item-meta">
                          <span className={`skillcenter-status ${statusTone(space.status)}`}>{statusLabel(space.status)}</span>
                          <span className="skillcenter-meta-text" title={space.projectName || "default"}>Project · {space.projectName || "default"}</span>
                          <span className="skillcenter-meta-text">{space.skillCount ?? 0} 个技能</span>
                          {space.updatedAt && <span className="skillcenter-meta-text">更新于 {updatedAtLabel(space.updatedAt)}</span>}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <Pager page={spacePage} total={spaceTotal} pageSize={SPACE_PAGE_SIZE} onPage={setSpacePage} />
          </section>

          <section className="skillcenter-panel" aria-label="技能列表">
            {!selectedSpace ? (
              <EmptyState>点击 Skill 空间以查看详情</EmptyState>
            ) : (
              <>
                <header className="skillcenter-panel-head">
                  <div><h2 title={selectedSpace.name}>{selectedSpace.name} · 技能</h2></div>
                  <span>{skillTotal}</span>
                </header>
                <div className="skillcenter-listwrap">
                  {skillsLoading && <div className="skillcenter-loading skillcenter-loading--overlay"><LoadingMark />正在读取技能…</div>}
                  {skillsError ? (
                    <div className="skillcenter-error">{skillsError}</div>
                  ) : skills.length === 0 && !skillsLoading ? (
                    <EmptyState>这个空间中暂无技能</EmptyState>
                  ) : (
                    <div className="skillcenter-list skillcenter-list--skills">
                      {skills.map((skill) => (
                        <button type="button" key={`${skill.skillId}:${skill.version}`} className="skillcenter-skill-item" onClick={() => void openDetail(skill)}>
                          <span className="skillcenter-item-body">
                            <span className="skillcenter-item-title" title={skill.skillName}>{skill.skillName}</span>
                            <span className="skillcenter-item-description">{skill.skillDescription || "暂无描述"}</span>
                            <span className="skillcenter-item-meta">
                              <span className={`skillcenter-status ${statusTone(skill.skillStatus)}`}>{statusLabel(skill.skillStatus)}</span>
                              <span className="skillcenter-meta-text">版本 · {skill.version || "—"}</span>
                            </span>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <Pager page={skillPage} total={skillTotal} pageSize={SKILL_PAGE_SIZE} onPage={setSkillPage} />
              </>
            )}
          </section>
      </div>

      {detailSkill && selectedSpace && (
        <SkillDetailDialog
          skill={detailSkill}
          space={selectedSpace}
          region={region}
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onClose={closeDetail}
        />
      )}
    </section>
  );
}
