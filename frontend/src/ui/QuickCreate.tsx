import { useRef, useState } from "react";
import { MessagesSquare, Wand2, LayoutTemplate, Workflow, Upload } from "lucide-react";
import { StackCards, type StackCardDef } from "./AddAgentMenu";
import { yamlToDraft } from "../create/configYaml";
import type { AgentDraft } from "../create/types";

export type QuickCreateKind = "intelligent" | "custom" | "template" | "workflow";

const MODES: { kind: QuickCreateKind; icon: StackCardDef["icon"]; title: string; desc: string; disabled?: boolean }[] = [
  { kind: "custom", icon: Wand2, title: "自定义", desc: "分步配置模型、工具、记忆、知识库等组件。" },
  { kind: "intelligent", icon: MessagesSquare, title: "智能模式", desc: "敬请期待", disabled: true },
  { kind: "template", icon: LayoutTemplate, title: "从模板新建", desc: "敬请期待", disabled: true },
  { kind: "workflow", icon: Workflow, title: "工作流", desc: "敬请期待", disabled: true },
];

export interface QuickCreateProps {
  onSelect: (kind: QuickCreateKind) => void;
  /** Import an agent-structure YAML to prefill the custom wizard. */
  onImport: (draft: AgentDraft) => void;
}

export function QuickCreate({ onSelect, onImport }: QuickCreateProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState("");

  const cards: StackCardDef[] = MODES.map((m) => ({
    key: m.kind,
    icon: m.icon,
    title: m.title,
    desc: m.desc,
    disabled: m.disabled,
    onClick: () => onSelect(m.kind),
  }));

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-importing the same file
    if (!file) return;
    try {
      const text = await file.text();
      onImport(yamlToDraft(text));
    } catch (ex) {
      setErr(`导入失败：${ex instanceof Error ? ex.message : String(ex)}`);
    }
  };

  return (
    <StackCards
      title="从 0 快速创建"
      sub="选择一种方式开始"
      cards={cards}
      footer={
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <button className="stk-import" onClick={() => fileRef.current?.click()}>
            <Upload />
            导入 YAML 配置
          </button>
          {err && <span style={{ fontSize: 12, color: "hsl(var(--destructive))" }}>{err}</span>}
          <input
            ref={fileRef}
            type="file"
            accept=".yaml,.yml,text/yaml"
            style={{ display: "none" }}
            onChange={onFile}
          />
        </div>
      }
    />
  );
}
