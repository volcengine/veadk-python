import { ErrorState } from "../../components/primitives/ErrorState";

import "./ErrorStatePreview.css";

export function ErrorStatePreview() {
  return (
    <section aria-labelledby="error-state-preview-title">
      <h2 data-preview-heading tabIndex={-1} id="error-state-preview-title" className="component-preview-title">Default</h2>
      <div className="error-state-preview__frame">
        <ErrorState
          title="资源加载失败"
          description="请检查网络连接后重试，或稍后重新打开此页面"
        />
      </div>
    </section>
  );
}
