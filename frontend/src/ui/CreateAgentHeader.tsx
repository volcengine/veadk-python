import { Button } from "@openai/apps-sdk-ui/components/Button";
import { SegmentedControl } from "@openai/apps-sdk-ui/components/SegmentedControl";
import {
  CreateAddIcon,
  CreateBackIcon,
  CreateCloseIcon,
  CreateDebugIcon,
  CreateDeployIcon,
  CreateDownloadIcon,
} from "./icons/CreateAgentIcons";
import "./CreateAgentHeader.css";

export interface CreateAgentHeaderProps {
  onBack: () => void;
  onDebug?: () => void;
  onDeploy?: () => void;
  debugMode?: boolean;
  showDebugPreview?: boolean;
  comparisonDisabled?: boolean;
  onAddComparison?: () => void;
  onExitDebug?: () => void;
}

export function CreateAgentHeader({
  onBack,
  onDebug,
  onDeploy,
  debugMode = false,
  showDebugPreview = true,
  comparisonDisabled = false,
  onAddComparison,
  onExitDebug,
}: CreateAgentHeaderProps) {
  const workspace = Boolean(onDebug || onDeploy);
  const stateClass = debugMode
    ? showDebugPreview
      ? "is-debug-preview"
      : "is-debug-results"
    : workspace
      ? "is-build"
      : "is-entry";

  return (
    <header
      className={`create-agent-header ${stateClass}${workspace ? " is-workspace" : ""}`}
    >
      <div className="create-agent-header-start">
        <Button
          type="button"
          color="secondary"
          variant="ghost"
          size="sm"
          uniform
          pill={false}
          className="create-agent-header-back"
          aria-label="返回创建入口"
          onClick={onBack}
        >
          <CreateBackIcon />
        </Button>
        <span className="create-agent-header-title">创建智能体</span>
      </div>

      {debugMode && showDebugPreview && (
        <SegmentedControl
          className="create-agent-header-preview"
          value="canvas"
          size="sm"
          gutterSize="sm"
          pill
          aria-label="调试预览"
        >
          <SegmentedControl.Option value="canvas">画布预览</SegmentedControl.Option>
          <SegmentedControl.Option value="list" disabled>
            列表预览
          </SegmentedControl.Option>
        </SegmentedControl>
      )}

      <div
        className="create-agent-header-actions"
        role="group"
        aria-label="创建工具"
      >
        {debugMode ? (
          <>
            <Button
              type="button"
              color="secondary"
              variant="ghost"
              size="sm"
              pill={false}
              className="create-agent-header-debug-action is-add"
              disabled={comparisonDisabled}
              onClick={onAddComparison}
            >
              <CreateAddIcon />
              添加对照
            </Button>
            <Button
              type="button"
              color="secondary"
              variant="outline"
              size="sm"
              pill={false}
              className="create-agent-header-debug-action"
              onClick={onExitDebug}
            >
              <CreateCloseIcon />
              退出调试
            </Button>
          </>
        ) : (
          <Button
            type="button"
            color="secondary"
            variant="ghost"
            size="sm"
            pill={false}
            inert
            className="create-agent-header-action is-code"
          >
            <CreateDownloadIcon />
            代码
          </Button>
        )}
        {!debugMode && (
          <>
            <Button
              type="button"
              color="secondary"
              variant="outline"
              size="sm"
              pill={false}
              className="create-agent-header-action is-debug"
              onClick={onDebug}
            >
              <CreateDebugIcon />
              调试
            </Button>
            <Button
              type="button"
              color="primary"
              size="sm"
              pill={false}
              className="create-agent-header-action is-deploy"
              onClick={onDeploy}
            >
              <CreateDeployIcon />
              部署
            </Button>
          </>
        )}
      </div>
    </header>
  );
}
