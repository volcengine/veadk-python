import { StudioUpdateControl } from "../StudioUpdateControl";
import { parseReleaseNotes } from "../releaseNotes";

const DEFAULT_RELEASE_NOTES = [
  "多地域智能体：并行加载北京与上海 Runtime，列表下滑即可继续加载。",
  "会话内切换：在输入框旁选择智能体，并直接开启一段新会话。",
  "可视化执行画布：通过横向画布查看多智能体结构，并支持全屏浏览。",
] as const;

const bundledReleaseNotes = parseReleaseNotes(
  import.meta.env.VITE_STUDIO_RELEASE_CHANGELOG,
);
const releaseNotes = bundledReleaseNotes.length
  ? bundledReleaseNotes
  : DEFAULT_RELEASE_NOTES;

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
      <section
        id="welcome-feature-popover"
        className="welcome-feature-popover"
        role="tooltip"
      >
        <strong>本次更新</strong>
        <ul>
          {releaseNotes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </section>
      {canUpdate && <StudioUpdateControl variant="feature-link" />}
    </div>
  );
}
