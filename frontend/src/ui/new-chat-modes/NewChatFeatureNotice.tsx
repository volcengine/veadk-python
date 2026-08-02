import { StudioUpdateControl } from "../StudioUpdateControl";

const FEATURES = [
  {
    title: "多地域智能体",
    description: "并行加载北京与上海 Runtime，列表下滑即可继续加载。",
  },
  {
    title: "会话内切换",
    description: "在输入框旁选择智能体，并直接开启一段新会话。",
  },
  {
    title: "可视化执行画布",
    description: "通过横向画布查看多智能体结构，并支持全屏浏览。",
  },
] as const;

export function NewChatFeatureNotice({ canUpdate = false }: { canUpdate?: boolean }) {
  return (
    <div className="welcome-feature-pill">
      <span>焕然一新</span>
      <span className="welcome-feature-divider" aria-hidden="true" />
      <button
        type="button"
        className="welcome-feature-link"
        aria-describedby="welcome-feature-popover"
      >
        查看新特性
      </button>
      {canUpdate && <StudioUpdateControl variant="feature-link" />}
      <section
        id="welcome-feature-popover"
        className="welcome-feature-popover"
        role="tooltip"
      >
        <strong>本次更新</strong>
        <ul>
          {FEATURES.map((feature) => (
            <li key={feature.title}>
              <span>{feature.title}</span>
              <p>{feature.description}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
