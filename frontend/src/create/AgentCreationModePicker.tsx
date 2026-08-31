import { useRef, useState } from "react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { motion, useReducedMotion } from "motion/react";
import { ResourceIdentityMark } from "../ui/ResourceCollection";

import "./AgentCreationModePicker.css";

export interface AgentCreationModePickerProps {
  onSelectVulcan: () => void;
  onSelectTraditional: () => void;
}

type FeatureIconName =
  | "branch"
  | "plan"
  | "collaborate"
  | "summary"
  | "skills"
  | "trace"
  | "structure"
  | "model"
  | "environment"
  | "deploy"
  | "workflow";

function FeatureIcon({ name }: { name: FeatureIconName }) {
  const commonProps = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  switch (name) {
    case "branch":
      return (
        <svg {...commonProps}>
          <circle cx="6" cy="5" r="2" />
          <circle cx="18" cy="7" r="2" />
          <circle cx="18" cy="17" r="2" />
          <path d="M8 5h2.5A3.5 3.5 0 0 1 14 8.5v7A1.5 1.5 0 0 0 15.5 17H16" />
          <path d="M14 10.5v-2A1.5 1.5 0 0 1 15.5 7H16" />
        </svg>
      );
    case "plan":
      return (
        <svg {...commonProps}>
          <path d="M6.5 3.5h11a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2Z" />
          <path d="m8 9 1.4 1.4L12 7.8M13.5 10H16M8 15l1.4 1.4 2.6-2.6M13.5 16H16" />
        </svg>
      );
    case "collaborate":
      return (
        <svg {...commonProps}>
          <circle cx="8" cy="8" r="3" />
          <circle cx="17" cy="9" r="2.5" />
          <path d="M3.5 19a4.5 4.5 0 0 1 9 0M13.5 15.5A4 4 0 0 1 20.5 18" />
        </svg>
      );
    case "summary":
      return (
        <svg {...commonProps}>
          <path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" />
        </svg>
      );
    case "skills":
      return (
        <svg {...commonProps}>
          <path d="M5 5h5v5H5zM14 5h5v5h-5zM5 14h5v5H5z" />
          <path d="M14 16.5h5M16.5 14v5" />
        </svg>
      );
    case "trace":
      return (
        <svg {...commonProps}>
          <circle cx="6" cy="6" r="2" />
          <circle cx="18" cy="12" r="2" />
          <circle cx="8" cy="18" r="2" />
          <path d="M8 6h3a3 3 0 0 1 3 3v0a3 3 0 0 0 2 2.83M16.2 13.2 9.8 16.8" />
        </svg>
      );
    case "structure":
      return (
        <svg {...commonProps}>
          <rect x="3.5" y="4" width="7" height="5" rx="1" />
          <rect x="13.5" y="15" width="7" height="5" rx="1" />
          <path d="M10.5 6.5h3A3.5 3.5 0 0 1 17 10v5M7 9v7a2 2 0 0 0 2 2h4.5" />
        </svg>
      );
    case "model":
      return (
        <svg {...commonProps}>
          <path d="M8 3.5v3M16 3.5v3M8 17.5v3M16 17.5v3M3.5 8h3M17.5 8h3M3.5 16h3M17.5 16h3" />
          <rect x="6.5" y="6.5" width="11" height="11" rx="2" />
          <path d="M10 10h4v4h-4z" />
        </svg>
      );
    case "environment":
      return (
        <svg {...commonProps}>
          <path d="M4 7.5h16M7 4h10l3 3.5v10L17 20H7l-3-2.5v-10Z" />
          <path d="m8 12 2 2-2 2M12.5 16H16" />
        </svg>
      );
    case "deploy":
      return (
        <svg {...commonProps}>
          <path d="M12 3.5v11M7.5 8 12 3.5 16.5 8" />
          <path d="M5 13.5v5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5v-5" />
        </svg>
      );
    case "workflow":
      return (
        <svg {...commonProps}>
          <rect x="4" y="4" width="6" height="5" rx="1" />
          <rect x="14" y="15" width="6" height="5" rx="1" />
          <path d="M10 6.5h2a4 4 0 0 1 4 4V15M7 9v3a4 4 0 0 0 4 4h3" />
        </svg>
      );
  }
}

export function AgentCreationModePicker({
  onSelectVulcan,
  onSelectTraditional,
}: AgentCreationModePickerProps) {
  const reduceMotion = useReducedMotion();
  const [isLeaving, setIsLeaving] = useState(false);
  const pendingSelectionRef = useRef<(() => void) | null>(null);

  const selectMode = (onSelect: () => void) => {
    if (isLeaving) return;
    if (reduceMotion) {
      onSelect();
      return;
    }
    pendingSelectionRef.current = onSelect;
    setIsLeaving(true);
  };

  const finishTransition = () => {
    if (!isLeaving) return;
    const onSelect = pendingSelectionRef.current;
    pendingSelectionRef.current = null;
    onSelect?.();
  };

  return (
    <motion.main
      className={`agent-creation-mode-picker${isLeaving ? " is-leaving" : ""}`}
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: isLeaving ? 0 : 1 }}
      transition={{
        duration: isLeaving ? 0.12 : 0.18,
        ease: [0.16, 1, 0.3, 1],
      }}
      onAnimationComplete={finishTransition}
    >
      <section
        className="agent-creation-mode-picker__content"
        aria-labelledby="agent-creation-mode-picker-title"
      >
        <header className="agent-creation-mode-picker__header">
          <h1 id="agent-creation-mode-picker-title">选择创建方式</h1>
          <p>以不同模式构建您的智能体</p>
        </header>

        <div className="agent-creation-mode-picker__options">
          <Button
            type="button"
            className="agent-creation-mode-picker__card"
            color="secondary"
            variant="outline"
            pill={false}
            block
            onClick={() => selectMode(onSelectVulcan)}
          >
            <span className="agent-creation-mode-picker__card-header">
              <ResourceIdentityMark
                className="agent-creation-mode-picker__avatar is-vulcan"
                seed="快速模式"
              />
              <span className="agent-creation-mode-picker__card-copy">
                <span className="agent-creation-mode-picker__card-title">
                  快速模式
                </span>
                <span className="agent-creation-mode-picker__card-description">
                  动态派生子智能体自主完成任务
                </span>
              </span>
            </span>
            <span
              className="agent-creation-mode-picker__divider"
              aria-hidden="true"
            />
            <span className="agent-creation-mode-picker__features">
              <span>特性</span>
              <span className="agent-creation-mode-picker__feature-grid">
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="branch" />
                  </span>
                  <span>动态派生子智能体</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="plan" />
                  </span>
                  <span>自主规划执行</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="collaborate" />
                  </span>
                  <span>多智能体协作</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="summary" />
                  </span>
                  <span>自动汇总结果</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="skills" />
                  </span>
                  <span>按需调用技能</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="trace" />
                  </span>
                  <span>任务过程可追踪</span>
                </span>
              </span>
            </span>
          </Button>

          <Button
            type="button"
            className="agent-creation-mode-picker__card"
            color="secondary"
            variant="outline"
            pill={false}
            block
            onClick={() => selectMode(onSelectTraditional)}
          >
            <span className="agent-creation-mode-picker__card-header">
              <ResourceIdentityMark
                className="agent-creation-mode-picker__avatar is-traditional"
                seed="传统模式"
              />
              <span className="agent-creation-mode-picker__card-copy">
                <span className="agent-creation-mode-picker__card-title">
                  传统模式
                </span>
                <span className="agent-creation-mode-picker__card-description">
                  高度自定义您的智能体结构
                </span>
              </span>
            </span>
            <span
              className="agent-creation-mode-picker__divider"
              aria-hidden="true"
            />
            <span className="agent-creation-mode-picker__features">
              <span>特性</span>
              <span className="agent-creation-mode-picker__feature-grid">
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="structure" />
                  </span>
                  <span>可视化配置</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="model" />
                  </span>
                  <span>存量智能体迁移</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="environment" />
                  </span>
                  <span>实时调试</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="deploy" />
                  </span>
                  <span>可选性能优化</span>
                </span>
                <span className="agent-creation-mode-picker__feature">
                  <span className="agent-creation-mode-picker__feature-icon">
                    <FeatureIcon name="workflow" />
                  </span>
                  <span>精细参数控制</span>
                </span>
              </span>
            </span>
          </Button>
        </div>
      </section>
    </motion.main>
  );
}
