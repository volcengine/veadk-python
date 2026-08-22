import { useState, type ComponentType, type SVGProps } from "react";
import { isImeCompositionEvent } from "../ui/composerKeyboard";
import { CreateNavbar } from "./CreateNavbar";
import "./CreateCanvas.css";

interface CreateCanvasProps {
  onBack: () => void;
  onPromptSubmit: (prompt: string) => void;
  onBlank: () => void;
  onUploadPackage: () => void;
  onMigration: () => void;
}

interface CreateShortcut {
  key: string;
  title: string;
  description: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  onClick: () => void;
}

function BlankCreateIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M7.65 18.65V5.65a1 1 0 0 0-1-1h-5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5a1 1 0 0 0-1-1h-13M12.65.65h5a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1Z"
        transform="translate(2.35 2.35)"
        stroke="#101013"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function UploadCodeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M12.018.587a.75.75 0 0 1 1.464.326l-4 18a.75.75 0 1 1-1.464-.326l4-18ZM5.22 4.22a.75.75 0 0 1 1.06 1.061L1.81 9.75l4.47 4.47a.75.75 0 0 1-1.06 1.061l-5-5a.75.75 0 0 1 0-1.061l5-5Zm10 0a.75.75 0 0 1 1.06 0l5 5a.75.75 0 0 1 0 1.061l-5 5a.75.75 0 0 1-1.06-1.061l4.469-4.47-4.47-4.469a.75.75 0 0 1 0-1.061Z"
        transform="translate(1.25 2.249)"
        fill="#101013"
      />
    </svg>
  );
}

function MigrationCubeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="m10.65 7.457-7.936 5.159c-.688.447-1.032.67-1.151.954a1 1 0 0 0 0 .775m9.087-6.888 7.936 5.159c.688.447 1.032.67 1.151.954a1 1 0 0 1 0 .775M10.65 7.457v-6.5m0 12.5L2.714 8.3c-.688-.447-1.032-.671-1.151-.954a1 1 0 0 1 0-.775m9.087 6.888 7.936-5.158c.688-.447 1.032-.671 1.151-.954a1 1 0 0 0 0-.775M10.65 13.457v6.5m9.272-5.527-8.4 5.46c-.316.206-.473.308-.643.348a1 1 0 0 1-.457 0c-.17-.04-.328-.142-.644-.347l-8.4-5.46c-.266-.173-.399-.26-.495-.375a1 1 0 0 1-.189-.347C.65 13.565.65 13.406.65 13.089V7.826c0-.318 0-.476.044-.62a1 1 0 0 1 .189-.347c.096-.115.229-.202.495-.375l8.4-5.46c.316-.205.474-.308.644-.348a1 1 0 0 1 .457 0c.17.04.327.143.643.348l8.4 5.46c.266.173.399.26.495.375a1 1 0 0 1 .189.347c.044.144.044.302.044.62v5.263c0 .317 0 .476-.044.62a1 1 0 0 1-.189.347c-.096.115-.229.202-.495.374Z"
        transform="translate(1.35 1.543)"
        stroke="#101013"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CreateAgentIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 36 36" fill="none" aria-hidden="true" {...props}>
      <g transform="translate(4.1537 4.1537)">
        <path
          d="M20.77 0v6.923h6.922v6.924L13.847 27.692H0V0h20.77ZM6.923 20.77H20.77V6.923H6.923V20.77Z"
          fill="#000"
        />
        <path d="M20.77 20.77h6.922v6.922H20.77z" fill="#000" />
      </g>
    </svg>
  );
}

function SendIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="M10 15.5v-11m0 0L5.5 9M10 4.5 14.5 9"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function CreateCanvas({
  onBack,
  onPromptSubmit,
  onBlank,
  onUploadPackage,
  onMigration,
}: CreateCanvasProps) {
  const [prompt, setPrompt] = useState("");
  const shortcuts: CreateShortcut[] = [
    {
      key: "blank",
      title: "从空白创建",
      description: "手动配置智能体",
      icon: BlankCreateIcon,
      onClick: onBlank,
    },
    {
      key: "package",
      title: "上传代码包",
      description: "查看代码并一键部署",
      icon: UploadCodeIcon,
      onClick: onUploadPackage,
    },
    {
      key: "migration",
      title: "存量迁移",
      description: "从 LangChain/Dify 等迁移",
      icon: MigrationCubeIcon,
      onClick: onMigration,
    },
  ];

  function submitPrompt() {
    const value = prompt.trim();
    if (value) onPromptSubmit(value);
  }

  return (
    <section className="create-canvas" aria-label="创建 Agent">
      <CreateNavbar
        onBack={onBack}
        codeDisabled
        primaryLabel="部署"
        backLabel="返回智能体列表"
      />

      <div className="create-canvas__hero">
        <div className="create-canvas__hero-title">
          <CreateAgentIcon />
          <h2>描述你想创建的智能体</h2>
        </div>
        <div className="create-canvas__composer">
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !isImeCompositionEvent(event.nativeEvent)
              ) {
                event.preventDefault();
                submitPrompt();
              }
            }}
            rows={1}
            autoFocus
            placeholder="请描述你想创建的智能体"
            aria-label="智能体描述"
          />
          <button
            type="button"
            className="create-canvas__send"
            onClick={submitPrompt}
            disabled={!prompt.trim()}
            aria-label="发送智能体描述"
          >
            <SendIcon />
          </button>
        </div>
      </div>

      <div className="create-canvas__shortcuts" aria-label="其他创建方式">
        {shortcuts.map((shortcut) => {
          const Icon = shortcut.icon;
          return (
            <button
              key={shortcut.key}
              type="button"
              className="create-canvas__shortcut"
              onClick={shortcut.onClick}
            >
              <span className="create-canvas__shortcut-icon">
                <Icon />
              </span>
              <span className="create-canvas__shortcut-copy">
                <span className="create-canvas__shortcut-title">
                  {shortcut.title}
                </span>
                <span className="create-canvas__shortcut-description">
                  {shortcut.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
