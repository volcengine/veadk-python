import { useRef, useState } from "react";
import { IndexLayout } from "../../components/layouts/IndexLayout";
import { GlassTabs } from "../../components/primitives/GlassTabs";
import { PromptInput } from "../../components/ai-app/PromptInput";
import { Item } from "../../components/composites/Item";
import blocksIcon from "../../components/layouts/IndexLayout/assets/blocks.svg";
import codepenIcon from "../../components/layouts/IndexLayout/assets/codepen.svg";
import { ComponentApi } from "../api/ComponentApi";
import { promptPlaceholders } from "./promptInputExamples";
import "./IndexLayoutPreview.css";

export function IndexLayoutPreview() {
  const [mode, setMode] = useState("development");
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const focusPrompt = () => promptRef.current?.focus();

  return (
    <section aria-labelledby="index-layout-preview-title">
      <h2 className="component-preview-title" id="index-layout-preview-title">Index layout</h2>
      <IndexLayout
        tabs={<GlassTabs
          aria-label="Workspace mode"
          items={[{ value: "development", label: "Development" }, { value: "daily-work", label: "Daily Work" }]}
          value={mode}
          onValueChange={setMode}
        />}
        prompt={<PromptInput ref={promptRef} placeholders={promptPlaceholders} aria-label="Describe the agent you want to create" />}
        shortcuts={<>
          <Item variant="compact" title="From template" description="Create from a template" onAction={focusPrompt}
            icon={<span className="index-layout-preview__shortcut-icon" style={{ maskImage: `url(${blocksIcon})` }} />} />
          <Item variant="compact" title="Upload code" description="View and one-click deploy" onAction={focusPrompt} />
          <Item variant="compact" title="Migrate existing" description="Migrate from LangChain" onAction={focusPrompt}
            icon={<span className="index-layout-preview__shortcut-icon" style={{ maskImage: `url(${codepenIcon})` }} />} />
        </>}
      />
      <ComponentApi names={["IndexLayout"]} />
    </section>
  );
}
