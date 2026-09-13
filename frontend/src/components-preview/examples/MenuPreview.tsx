import { useState } from "react";
import { ExternalLinkIcon } from "../../components/icons/ExternalLinkIcon";
import { PlusIcon } from "../../components/icons/PlusIcon";
import { Menu, type MenuEntry, type MenuItem } from "../../components/primitives/Menu";
import { ComponentApi } from "../api/ComponentApi";
import "./MenuPreview.css";

function DuplicateIcon() {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x="2.5" y="5.5" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.25" />
    <path d="M5.5 3.5v-1h8v8h-1" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

function FolderIcon() {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M2.5 4a1 1 0 0 1 1-1h3l1.5 2h4.5a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1V4Z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round" />
  </svg>;
}

const basicItems: readonly MenuEntry[] = [
  { id: "view", label: "查看详情" },
  { id: "rename", label: "重命名" },
  { id: "duplicate", label: "复制" },
];

const workspaceItems: readonly MenuEntry[] = [
  "产品设计", "前端开发", "后端开发", "质量保障", "数据分析", "基础设施",
  "客户支持", "产品运营", "市场推广", "技术文档", "公共模板", "个人空间",
].map(label => ({ id: label, label }));

const groupedItems: readonly MenuEntry[] = [
  { type: "group", id: "create", label: "创建", items: [
    { id: "new-project", label: "新建项目", icon: <PlusIcon /> },
    { id: "from-template", label: "从模板创建" },
  ] },
  { type: "separator", id: "create-management-separator" },
  { type: "group", id: "manage", label: "管理", items: [
    { id: "copy-project", label: "复制项目", icon: <DuplicateIcon /> },
    { id: "rename-project", label: "重命名" },
    { id: "open-project", label: "在新窗口打开", icon: <ExternalLinkIcon /> },
    { id: "archive-project", label: "归档项目", disabled: true },
  ] },
];

const nestedItems: readonly MenuEntry[] = [
  { id: "move", label: "移动到", icon: <FolderIcon />, children: [
    { type: "group", id: "teams", label: "团队空间", items: [
      { id: "product", label: "产品团队", icon: <FolderIcon />, children: [
        { id: "current-sprint", label: "当前迭代" },
        { id: "product-archive", label: "产品归档" },
      ] },
      { id: "engineering", label: "研发团队", icon: <FolderIcon />, children: [
        { id: "frontend", label: "前端组件" },
        { id: "backend", label: "后端服务" },
      ] },
    ] },
    { type: "separator", id: "space-separator" },
    { id: "personal", label: "个人空间" },
  ] },
  { id: "export", label: "导出", children: [
    { id: "export-json", label: "JSON 文件" },
    { id: "export-yaml", label: "YAML 文件" },
  ] },
  { type: "separator", id: "nested-separator" },
  { id: "copy-link", label: "复制链接", icon: <ExternalLinkIcon /> },
];

const entryFields = [
  ["id", "string", "全部类型必填", "未设置", "菜单项、分组和分割线的稳定标识，同一个 Menu 内保持唯一"],
  ["type", "'item' | 'group' | 'separator'", "分组与分割线必填", "'item'", "item 为菜单项，group 为分组，separator 为分割线"],
  ["label", "string", "菜单项必填", "未设置", "菜单项文案或分组标题；分割线不使用此属性"],
  ["icon", "ReactNode", "否", "未设置", "菜单项左侧图标，可与无图标菜单项混排"],
  ["disabled", "boolean", "否", "false", "禁用菜单项，不能触发操作或打开子菜单"],
  ["children", "readonly MenuEntry[]", "否", "未设置", "菜单项的子菜单，可继续嵌套分组和多级菜单"],
  ["onSelect", "() => void", "否", "未设置", "末级菜单项选中时调用，同时触发 Menu 的 onSelect"],
  ["items", "readonly MenuEntry[]", "分组必填", "未设置", "分组包含的菜单项、子分组或分割线"],
] as const;

export function MenuPreview() {
  const [selection, setSelection] = useState("");

  function handleSelect(_id: string, item: MenuItem) {
    setSelection(item.label);
  }

  return <section aria-labelledby="menu-preview-title">
    <h2 id="menu-preview-title" className="component-preview-title">Menu</h2>
    <div className="menu-preview__examples">
      <section aria-labelledby="menu-basic-title">
        <h3 id="menu-basic-title">基础菜单</h3>
        <Menu label="操作" items={basicItems} onSelect={handleSelect} />
      </section>
      <section aria-labelledby="menu-grouped-title">
        <h3 id="menu-grouped-title">分组与图标</h3>
        <Menu label="项目操作" items={groupedItems} onSelect={handleSelect} />
      </section>
      <section aria-labelledby="menu-nested-title">
        <h3 id="menu-nested-title">多级菜单</h3>
        <Menu label="更多操作" items={nestedItems} onSelect={handleSelect} />
      </section>
      <section aria-labelledby="menu-state-title">
        <h3 id="menu-state-title">禁用与空状态</h3>
        <div className="menu-preview__states">
          <Menu label="不可用" items={basicItems} disabled />
          <Menu label="空菜单" items={[]} />
        </div>
      </section>
      <section aria-labelledby="menu-scroll-title">
        <h3 id="menu-scroll-title">长菜单</h3>
        <Menu label="选择空间" items={workspaceItems} maxHeight={200} onSelect={handleSelect} />
      </section>
      <section aria-labelledby="menu-hover-title">
        <h3 id="menu-hover-title">悬停展开</h3>
        <Menu label="悬停打开" items={groupedItems} openOnHover onSelect={handleSelect} />
      </section>
    </div>
    <section className="menu-preview__positioning" aria-labelledby="menu-positioning-title">
      <h3 id="menu-positioning-title">自动定位</h3>
      <p>根据按钮位置和窗口空间自动调整方向与对齐</p>
      <div className="menu-preview__positioning-row">
        <Menu label="左侧入口" items={groupedItems} onSelect={handleSelect} />
        <Menu label="右侧入口" items={nestedItems} onSelect={handleSelect} />
      </div>
    </section>
    <p className="menu-preview__feedback" role="status">{selection ? `已选择：${selection}` : "选择菜单项查看操作反馈"}</p>
    <ComponentApi names={["Menu"]} />
    <section className="component-api menu-preview__entry-api" aria-labelledby="menu-entry-title">
      <h3 id="menu-entry-title">MenuEntry 数据结构</h3>
      <div className="component-api__scroll">
        <table>
          <thead><tr><th scope="col">参数 / 属性</th><th scope="col">类型</th><th scope="col">必填</th><th scope="col">默认值</th><th scope="col">说明</th></tr></thead>
          <tbody>{entryFields.map(([name, type, required, defaultValue, description]) => <tr key={name}>
            <th scope="row">{name}</th><td>{type}</td><td>{required}</td><td>{defaultValue}</td><td>{description}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  </section>;
}
