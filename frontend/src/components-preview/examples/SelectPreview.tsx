import { ComponentApi } from "../api/ComponentApi";
import { Select, type SelectOption } from "../../components/primitives/Select";
import doubao from "../../components/primitives/Select/assets/doubao.svg";
import "./SelectPreview.css";

const describedModels: readonly SelectOption[] = [
  { value: "doubao-seed-2.0-pro", label: "Doubao-Seed-2.0-pro", description: "适合复杂任务与高质量内容生成" },
  { value: "doubao-seed-2.0-lite", label: "Doubao-Seed-2.0-lite", description: "适合日常对话与轻量任务" },
  { value: "doubao-seed-2.0-mini", label: "Doubao-Seed-2.0-mini", description: "适合简单问答与快速响应" },
  { value: "doubao-seed-1.6-thinking", label: "Doubao-Seed-1.6-thinking", description: "适合多步分析与推理任务" },
  { value: "doubao-seed-1.6-flash", label: "Doubao-Seed-1.6-flash", description: "适合实时交互与批量处理" },
  { value: "doubao-1.5-pro", label: "Doubao-1.5-pro", description: "适合文本总结与文档理解" },
  { value: "doubao-1.5-lite", label: "Doubao-1.5-lite", description: "当前环境暂不可用", disabled: true },
].map(option => ({ ...option, icon: <img src={doubao} alt="" style={{ width: 13.008, height: 14.6672 }} /> }));

export function SelectPreview() {
  return <section aria-labelledby="select-preview-title">
    <h2 id="select-preview-title" className="component-preview-title">Select</h2>
    <Select aria-label="Model" options={[
      { value: "doubao-seed-2.0-pro", label: "Doubao-Seed-2.0-pro", icon: <img src={doubao} alt="" style={{ width: 13.008, height: 14.6672 }} /> },
      ...[
        "Doubao-Seed-2.0-lite",
        "Doubao-Seed-2.0-mini",
        "Doubao-Seed-1.8",
        "Doubao-Seed-1.6",
        "Doubao-Seed-1.6-flash",
        "Doubao-Seed-1.6-thinking",
        "Doubao-1.5-pro",
        "Doubao-1.5-lite",
        "Doubao-1.5-thinking-pro",
      ].map(label => ({ value: label.toLowerCase(), label, icon: <img src={doubao} alt="" style={{ width: 13.008, height: 14.6672 }} /> })),
    ]} />
    <section className="select-preview-description" aria-labelledby="select-description-title">
      <h3 id="select-description-title">With description</h3>
      <Select aria-label="Model with description" options={describedModels} />
    </section>
  <ComponentApi names={["Select"]} />
    </section>;
}
