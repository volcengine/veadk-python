import { ErrorState } from "../../components/primitives/ErrorState";
import { ComponentApi } from "../api/ComponentApi";
import "./ErrorStatePreview.css";

export function ErrorStatePreview() {
  return (
    <section aria-labelledby="error-state-preview-title">
      <h2 id="error-state-preview-title" className="component-preview-title">Error State</h2>
      <div className="error-state-preview__frame">
        <ErrorState
          title="资源加载失败"
          description="请检查网络连接后重试，或稍后重新打开此页面"
        />
      </div>
      <ComponentApi names={["ErrorState"]} />
    </section>
  );
}
