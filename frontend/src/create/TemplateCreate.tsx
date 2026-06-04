import { useState } from "react";
import { motion } from "motion/react";
import {
  ArrowLeft,
  Headset,
  BarChart3,
  Languages,
  Code2,
  Microscope,
  Users,
  Wrench,
  Brain,
  BookOpen,
  Activity,
  Network,
  ChevronRight,
  type LucideIcon,
} from "lucide-react";
import { type CreateModeProps, type AgentDraft, emptyDraft } from "./types";
import "./TemplateCreate.css";

/** A gallery preset: an AgentDraft plus presentation metadata. */
interface Template {
  id: string;
  /** A small monochrome glyph rendered in currentColor (muted). */
  icon: LucideIcon;
  draft: AgentDraft;
}

/** Build a preset from a partial draft, filling the rest from emptyDraft(). */
function preset(over: Partial<AgentDraft>): AgentDraft {
  return { ...emptyDraft(), ...over };
}

const TEMPLATES: Template[] = [
  {
    id: "support",
    icon: Headset,
    draft: preset({
      name: "客服助手",
      description: "7×24 在线答疑，结合知识库与历史对话，稳定、礼貌地解决用户问题。",
      instruction:
        "你是一名专业、耐心的客服助手。请始终保持礼貌、友好的语气，" +
        "优先依据知识库中的资料回答用户问题；当资料不足以确定答案时，" +
        "如实告知用户并主动引导其提供更多信息，切勿编造。" +
        "回答尽量简洁、分点清晰，必要时给出操作步骤。",
      model: "doubao-1.5-pro-32k",
      knowledgebase: true,
      memory: { shortTerm: true, longTerm: true },
    }),
  },
  {
    id: "analyst",
    icon: BarChart3,
    draft: preset({
      name: "数据分析师",
      description: "运行代码完成统计与可视化，开启链路追踪，分析过程可观测、可复现。",
      instruction:
        "你是一名严谨的数据分析师。面对数据问题时，先厘清分析目标与口径，" +
        "再通过编写并运行代码完成清洗、统计与可视化。" +
        "每一步都要说明你的假设与方法，给出结论时附上关键数据支撑，" +
        "并指出潜在的偏差与局限。",
      model: "doubao-1.5-pro-32k",
      tools: ["code_runner"],
      tracing: true,
    }),
  },
  {
    id: "translator",
    icon: Languages,
    draft: preset({
      name: "翻译助手",
      description: "中英互译，忠实、通顺、地道，保留原文语气与专业术语。",
      instruction:
        "你是一名专业的翻译助手，精通中英互译。" +
        "请在忠实于原文含义的前提下，使译文自然、地道、符合目标语言表达习惯；" +
        "保留专有名词与专业术语的准确性，并尽量贴合原文的语气与风格。" +
        "仅输出译文，除非用户额外要求解释。",
      model: "doubao-1.5-pro-32k",
    }),
  },
  {
    id: "coder",
    icon: Code2,
    draft: preset({
      name: "代码助手",
      description: "编写、调试与重构代码，可运行代码验证结果，给出清晰可维护的实现。",
      instruction:
        "你是一名资深软件工程师。请根据需求编写正确、清晰、可维护的代码，" +
        "遵循目标语言的惯用风格与最佳实践。" +
        "在不确定时通过运行代码验证你的实现，给出关键的边界条件与测试思路，" +
        "并对复杂逻辑附上简要注释。",
      model: "doubao-1.5-pro-32k",
      tools: ["code_runner", "file_reader"],
      tracing: true,
    }),
  },
  {
    id: "researcher",
    icon: Microscope,
    draft: preset({
      name: "研究员",
      description: "联网检索一手资料，结合知识库与长期记忆，输出有据可查的研究结论。",
      instruction:
        "你是一名严谨的研究员。面对研究问题时，先拆解关键子问题，" +
        "再通过联网检索收集多个一手、可信的来源，交叉验证后再下结论。" +
        "结论需注明出处与不确定性，区分事实与推断，避免以偏概全。",
      model: "doubao-1.5-pro-32k",
      tools: ["web_search"],
      knowledgebase: true,
      memory: { shortTerm: true, longTerm: true },
    }),
  },
  {
    id: "research-team",
    icon: Users,
    draft: preset({
      name: "多智能体研究团队",
      description: "由检索员、分析员、撰写员协作的研究编排，分工完成端到端调研报告。",
      instruction:
        "你是一支研究团队的总协调者。负责拆解用户的研究任务，" +
        "将检索、分析、撰写分别委派给对应的子 Agent，" +
        "汇总各子 Agent 的产出，把控整体质量，最终输出结构清晰、有据可查的研究报告。",
      model: "doubao-1.5-pro-32k",
      tracing: true,
      memory: { shortTerm: true, longTerm: true },
      subAgents: [
        preset({
          name: "检索员",
          description: "联网搜集与课题相关的一手资料与数据。",
          instruction:
            "你是研究团队中的检索员。根据课题联网检索多个可信来源，" +
            "整理出关键事实、数据与原文出处，交付给分析员，不做主观结论。",
          tools: ["web_search"],
        }),
        preset({
          name: "分析员",
          description: "对检索到的材料做交叉验证与归纳分析。",
          instruction:
            "你是研究团队中的分析员。对检索员提供的材料做交叉验证、归纳与对比，" +
            "提炼洞见、识别矛盾与不确定性，形成结构化的分析要点。",
          tools: ["code_runner"],
        }),
        preset({
          name: "撰写员",
          description: "将分析结论组织为结构清晰、引用规范的报告。",
          instruction:
            "你是研究团队中的撰写员。把分析员的要点组织成结构清晰、" +
            "语言通顺、引用规范的研究报告，确保每个结论都能追溯到来源。",
        }),
      ],
    }),
  },
];

/** Which built-in components a draft uses → tags on the card. */
function components(d: AgentDraft) {
  const out: { icon: LucideIcon; label: string }[] = [];
  if (d.tools.length) out.push({ icon: Wrench, label: "工具" });
  if (d.memory.shortTerm || d.memory.longTerm) out.push({ icon: Brain, label: "记忆" });
  if (d.knowledgebase) out.push({ icon: BookOpen, label: "知识库" });
  if (d.tracing) out.push({ icon: Activity, label: "观测" });
  if (d.subAgents.length) out.push({ icon: Network, label: `子Agent ${d.subAgents.length}` });
  return out;
}

export function TemplateCreate({ onBack, onCreate }: CreateModeProps) {
  const [selected, setSelected] = useState<Template | null>(null);
  // `onBack` is kept in props (an app-level breadcrumb handles leaving this
  // mode); we intentionally do not render a top-level back control here.
  void onBack;

  return (
    <div className="tpl-root">
      {selected ? (
        <TemplateDetail
          template={selected}
          onBack={() => setSelected(null)}
          onCreate={onCreate}
        />
      ) : (
        <Gallery onPick={setSelected} />
      )}
    </div>
  );
}

/* ---------------- gallery ---------------- */

function Gallery({ onPick }: { onPick: (t: Template) => void }) {
  return (
    <div className="tpl-scroll">
      <div className="tpl-head">
        <h1 className="tpl-title">从模板新建</h1>
        <p className="tpl-sub">选择一个预制 agent 模板，按需微调后即可创建。</p>
      </div>
      <div className="tpl-grid">
        {TEMPLATES.map((t, i) => (
          <motion.button
            key={t.id}
            type="button"
            className="tpl-card"
            onClick={() => onPick(t)}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03, duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
          >
            <span className="tpl-card-icon">
              <t.icon className="icon" />
            </span>
            <span className="tpl-card-name">{t.draft.name}</span>
            <span className="tpl-card-desc">{t.draft.description}</span>
          </motion.button>
        ))}
      </div>
    </div>
  );
}

/* ---------------- detail / preview ---------------- */

function TemplateDetail({
  template,
  onBack,
  onCreate,
}: {
  template: Template;
  onBack: () => void;
  onCreate: (draft: AgentDraft) => void;
}) {
  const [name, setName] = useState(template.draft.name);
  const Icon = template.icon;
  const tags = components(template.draft);

  function handleCreate() {
    const finalName = name.trim() || template.draft.name;
    onCreate({ ...template.draft, name: finalName });
  }

  return (
    <div className="tpl-scroll tpl-scroll--detail">
      <button className="tpl-back" onClick={onBack}>
        <ArrowLeft className="icon" /> 返回模板列表
      </button>
      <motion.div
        className="tpl-detail"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="tpl-detail-head">
          <span className="tpl-detail-icon">
            <Icon className="icon" />
          </span>
          <div className="tpl-detail-headtext">
            <div className="tpl-detail-name">{template.draft.name}</div>
            <div className="tpl-detail-desc">{template.draft.description}</div>
          </div>
        </div>

        {tags.length > 0 && (
          <div className="tpl-tags tpl-tags--detail">
            {tags.map((c) => (
              <span className="tpl-tag" key={c.label}>
                <c.icon className="tpl-tag-icon" /> {c.label}
              </span>
            ))}
          </div>
        )}

        <label className="tpl-field">
          <span className="tpl-field-label">名称</span>
          <input
            className="tpl-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={template.draft.name}
          />
        </label>

        <div className="tpl-field">
          <span className="tpl-field-label">系统提示词</span>
          <p className="tpl-instruction">{template.draft.instruction}</p>
        </div>

        <div className="tpl-meta-grid">
          {template.draft.model && (
            <div className="tpl-meta">
              <span className="tpl-meta-key">模型</span>
              <span className="tpl-meta-val tpl-mono">{template.draft.model}</span>
            </div>
          )}
          <div className="tpl-meta">
            <span className="tpl-meta-key">工具</span>
            <span className="tpl-meta-val">
              {template.draft.tools.length ? template.draft.tools.join("、") : "无"}
            </span>
          </div>
          <div className="tpl-meta">
            <span className="tpl-meta-key">记忆</span>
            <span className="tpl-meta-val">{memoryLabel(template.draft)}</span>
          </div>
          <div className="tpl-meta">
            <span className="tpl-meta-key">知识库</span>
            <span className="tpl-meta-val">{template.draft.knowledgebase ? "已开启" : "关闭"}</span>
          </div>
          <div className="tpl-meta">
            <span className="tpl-meta-key">观测追踪</span>
            <span className="tpl-meta-val">{template.draft.tracing ? "已开启" : "关闭"}</span>
          </div>
          <div className="tpl-meta">
            <span className="tpl-meta-key">A2UI</span>
            <span className="tpl-meta-val">{template.draft.enableA2ui ? "已开启" : "关闭"}</span>
          </div>
        </div>

        {template.draft.subAgents.length > 0 && (
          <div className="tpl-field">
            <span className="tpl-field-label">
              子 Agent（{template.draft.subAgents.length}）
            </span>
            <div className="tpl-subagents">
              {template.draft.subAgents.map((sub, i) => (
                <div className="tpl-subagent" key={i}>
                  <div className="tpl-subagent-top">
                    <span className="tpl-subagent-name">{sub.name}</span>
                    {sub.tools.length > 0 && (
                      <span className="tpl-subagent-tools">{sub.tools.join("、")}</span>
                    )}
                  </div>
                  <div className="tpl-subagent-desc">{sub.description}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <button className="tpl-create" onClick={handleCreate}>
          使用此模板创建 <ChevronRight className="icon" />
        </button>
      </motion.div>
    </div>
  );
}

function memoryLabel(d: AgentDraft): string {
  const parts: string[] = [];
  if (d.memory.shortTerm) parts.push("短期");
  if (d.memory.longTerm) parts.push("长期");
  return parts.length ? parts.join(" + ") : "关闭";
}
