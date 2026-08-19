import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { motion } from "motion/react";
import { useState, type FormEvent } from "react";
import { isImeCompositionEvent } from "./composerKeyboard";
import { CreateAgentHeader } from "./CreateAgentHeader";
import { AgentKitLogoIcon } from "./icons/AgentKitLogoIcon";
import { ComposerSendIcon } from "./icons/ComposerIcons";
import {
  CodePackageIcon,
  ExistingMigrationIcon,
  TemplateBlocksIcon,
} from "./icons/CreateAgentIcons";
import "./AddAgentMenu.css";

export interface AddAgentMenuProps {
  intelligentEnabled: boolean;
  intelligentLoading: boolean;
  intelligentReason?: string;
  onBack: () => void;
  onDescribe: (goal: string) => void;
  onTemplate: () => void;
  onPackage: () => void;
  onMigration: () => void;
}

export function AddAgentMenu({
  intelligentEnabled,
  intelligentLoading,
  intelligentReason,
  onBack,
  onDescribe,
  onTemplate,
  onPackage,
  onMigration,
}: AddAgentMenuProps) {
  const [goal, setGoal] = useState("");
  void intelligentEnabled;
  void intelligentLoading;
  void intelligentReason;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = goal.trim();
    if (!value) return;
    onDescribe(value);
  }

  const entries = [
    {
      key: "template",
      title: "从空白创建",
      description: "手动配置并创建智能体",
      icon: TemplateBlocksIcon,
      onClick: onTemplate,
    },
    {
      key: "package",
      title: "上传代码包",
      description: "查看代码并一键部署",
      icon: CodePackageIcon,
      onClick: onPackage,
    },
    {
      key: "migration",
      title: "存量迁移",
      description: "从 LangChain/Dify 等迁移",
      icon: ExistingMigrationIcon,
      onClick: onMigration,
    },
  ] as const;

  return (
    <section className="create-entry" aria-labelledby="create-entry-title">
      <CreateAgentHeader onBack={onBack} />

      <div className="create-entry-primary">
        <div className="create-entry-heading">
          <AgentKitLogoIcon className="create-entry-logo" />
          <h1 id="create-entry-title">描述你想创建的智能体</h1>
        </div>
        <form
          className="create-entry-form"
          autoComplete="off"
          onSubmit={submit}
        >
          <Input
            autoFocus
            value={goal}
            autoComplete="off"
            allowAutofillExtensions={false}
            onChange={(event) => setGoal(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !isImeCompositionEvent(event.nativeEvent)
              ) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="请描述你想创建的智能体"
            aria-label="智能体描述"
            size="3xl"
            gutterSize="xl"
            pill={false}
            className="create-entry-input"
            endAdornment={(
              <motion.button
                type="submit"
                className="comp-send create-entry-send"
                aria-label="开始创建"
                disabled={!goal.trim()}
                whileTap={goal.trim() ? { scale: 0.9 } : undefined}
                transition={{ type: "spring", stiffness: 600, damping: 22 }}
              >
                <ComposerSendIcon className="icon" />
              </motion.button>
            )}
          />
        </form>
      </div>

      <div className="create-entry-cards" aria-label="其他创建方式">
        {entries.map((entry) => {
          const Icon = entry.icon;
          return (
            <Button
              key={entry.key}
              type="button"
              color="secondary"
              variant="ghost"
              pill={false}
              block
              className={`create-entry-card is-${entry.key}`}
              onClick={entry.onClick}
            >
              <span className="create-entry-card-icon" aria-hidden="true">
                <Icon />
              </span>
              <span className="create-entry-card-copy">
                <span className="create-entry-card-title">{entry.title}</span>
                <span className="create-entry-card-description">
                  {entry.description}
                </span>
              </span>
            </Button>
          );
        })}
      </div>
    </section>
  );
}
