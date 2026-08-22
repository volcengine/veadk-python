import backIcon from "./assets/create-workspace/back.svg";
import downloadIcon from "./assets/create-workspace/download.svg";
import playIcon from "./assets/create-workspace/play.svg";
import publishIcon from "./assets/create-workspace/publish.svg";
import "./CreateNavbar.css";

interface CreateNavbarProps {
  onBack: () => void;
  onDebug?: () => void;
  onDeploy?: () => void;
  onExitDebug?: () => void;
  onAddComparison?: () => void;
  codeDisabled?: boolean;
  primaryLabel: "部署" | "发布";
  backLabel?: string;
  mode?: "create" | "debug" | "deploy";
}

export function CreateNavbar({
  onBack,
  onDebug,
  onDeploy,
  onExitDebug,
  onAddComparison,
  codeDisabled = false,
  primaryLabel,
  backLabel = "返回",
  mode = "create",
}: CreateNavbarProps) {
  return (
    <header className="create-navbar">
      <div className="create-navbar__start">
        <button
          type="button"
          className="create-navbar__back"
          onClick={onBack}
          aria-label={backLabel}
        >
          <img src={backIcon} alt="" />
        </button>
        <h1>创建智能体</h1>
      </div>

      {mode === "debug" ? (
        <div className="create-navbar__actions create-navbar__actions--debug" aria-label="调试操作">
          <button
            type="button"
            className="create-navbar__button create-navbar__button--compare"
            onClick={onAddComparison}
            onMouseUp={(event) => event.currentTarget.blur()}
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <g transform="translate(2.1667 2.1667) scale(.66667)">
                <path d="M8 16.75V9.5H.75C.335786 9.5 0 9.16421 0 8.75C0 8.33579.335786 8 .75 8H8V.75C8 .335786 8.33579 0 8.75 0C9.16421 0 9.5.335786 9.5.75V8H16.75C17.1642 8 17.5 8.33579 17.5 8.75C17.5 9.16421 17.1642 9.5 16.75 9.5H9.5V16.75C9.5 17.1642 9.16421 17.5 8.75 17.5C8.33579 17.5 8 17.1642 8 16.75Z" />
              </g>
            </svg>
            <span>添加对照</span>
          </button>
          <button
            type="button"
            className="create-navbar__button create-navbar__button--exit-debug"
            onClick={onExitDebug}
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <g transform="translate(2.8333 2.8333)">
                <path d="M9.47978.146447C9.67504-.0488153 9.99155-.0488155 10.1868.146447C10.3821.341709 10.3821.658216 10.1868.853478L5.87366 5.16663L10.1868 9.47978C10.3821 9.67504 10.3821 9.99155 10.1868 10.1868C9.99155 10.3821 9.67504 10.3821 9.47978 10.1868L5.16663 5.87366L.853478 10.1868C.658216 10.3821.341709 10.3821.146447 10.1868C-.0488155 9.99155-.0488153 9.67504.146447 9.47978L4.4596 5.16663L.146447.853478C-.0488155.658216-.0488155.341709.146447.146447C.341709-.0488155.658216-.0488155.853478.146447L5.16663 4.4596L9.47978.146447Z" />
              </g>
            </svg>
            <span>退出调试</span>
          </button>
        </div>
      ) : mode === "create" ? (
        <div className="create-navbar__actions" aria-label="创建步骤">
          <button
            type="button"
            className="create-navbar__button create-navbar__button--code"
            disabled={codeDisabled}
          >
            <span className="create-navbar__icon create-navbar__icon--code">
              <img src={downloadIcon} alt="" />
            </span>
            <span>代码</span>
          </button>
          <button
            type="button"
            className="create-navbar__button create-navbar__button--debug"
            onClick={onDebug}
          >
            <span className="create-navbar__icon create-navbar__icon--play">
              <img src={playIcon} alt="" />
            </span>
            <span>调试</span>
          </button>
          <button
            type="button"
            className="create-navbar__button create-navbar__button--primary"
            onClick={onDeploy}
          >
            <span className="create-navbar__icon create-navbar__icon--primary">
              <img src={publishIcon} alt="" />
            </span>
            <span>{primaryLabel}</span>
          </button>
        </div>
      ) : null}
    </header>
  );
}
