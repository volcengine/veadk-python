import { useState } from "react";
import { Drawer } from "../../components/composites/Drawer";
import { Button } from "../../components/primitives/Button";
import { ComponentApi } from "../api/ComponentApi";
import "./DrawerPreview.css";

const sections = [
  { title: "项目背景", description: "整理项目的背景资料与已有结论，方便团队了解工作的起点，以及需要继续确认的问题" },
  { title: "目标与范围", description: "明确本次工作的目标和交付内容，并记录相关约束，避免在协作过程中遗漏重要信息" },
  { title: "参考资料", description: "汇总相关文档、讨论记录与参考内容，为后续分析保留清晰的查阅路径" },
  { title: "实现说明", description: "记录方案中的主要决策和使用方式，让参与者能够快速理解当前结果" },
  { title: "验证记录", description: "保存关键验证过程与反馈，区分已经确认的结果和仍需进一步核实的内容" },
  { title: "后续事项", description: "列出接下来需要处理的工作，并在信息更新后补充到对应的资料中" },
];

export function DrawerPreview() {
  const [open, setOpen] = useState(false);
  return (
    <section aria-labelledby="drawer-preview-title">
      <h2 id="drawer-preview-title" className="component-preview-title">Drawer</h2>
      <Drawer
        open={open}
        onOpenChange={setOpen}
        trigger={<Button>打开 Drawer</Button>}
        title="资源详情"
        description="查看基础信息与内容摘要"
        footer={<Button onClick={() => setOpen(false)}>完成</Button>}
      >
        <div className="drawer-preview__content">
          <dl className="drawer-preview__metadata">
            <div><dt>名称</dt><dd>项目资料</dd></div>
            <div><dt>类型</dt><dd>文档集合</dd></div>
            <div><dt>更新时间</dt><dd>今天 14:30</dd></div>
          </dl>
          {sections.map(section => (
            <section key={section.title} className="drawer-preview__section">
              <h3>{section.title}</h3>
              <p>{section.description}</p>
            </section>
          ))}
        </div>
      </Drawer>
      <ComponentApi names={["Drawer"]} />
    </section>
  );
}
