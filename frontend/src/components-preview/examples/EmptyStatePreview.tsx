import { Button } from "../../components/primitives/Button";
import { EmptyState } from "../../components/primitives/EmptyState";
import { ComponentApi } from "../api/ComponentApi";
import "./EmptyStatePreview.css";

function SearchEmptyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m15.5 15.5 4.5 4.5M8 10.5h5" />
    </svg>
  );
}

export function EmptyStatePreview() {
  return (
    <section aria-labelledby="empty-state-preview-title">
      <h2 id="empty-state-preview-title" className="component-preview-title">Empty State</h2>
      <div className="empty-state-preview__examples">
        <section aria-labelledby="empty-state-resources-title">
          <h3 id="empty-state-resources-title" className="empty-state-preview__subtitle">基础空状态</h3>
          <div className="empty-state-preview__frame">
            <EmptyState
              title="暂无资源"
              description="创建你的第一个资源，或从本地导入已有资源"
              actions={<><Button>创建资源</Button><Button variant="secondary">导入资源</Button></>}
            />
          </div>
        </section>
        <section aria-labelledby="empty-state-search-title">
          <h3 id="empty-state-search-title" className="empty-state-preview__subtitle">自定义图标</h3>
          <div className="empty-state-preview__frame">
            <EmptyState
              icon={<SearchEmptyIcon />}
              title="没有找到匹配结果"
              description="试试其他关键词，或清除筛选条件查看全部资源"
              actions={<Button variant="secondary">清除筛选</Button>}
            />
          </div>
        </section>
      </div>
      <ComponentApi names={["EmptyState"]} />
    </section>
  );
}
