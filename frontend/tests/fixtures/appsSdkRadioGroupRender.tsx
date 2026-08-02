import { RadioGroup } from "@openai/apps-sdk-ui/components/RadioGroup";
import { renderToStaticMarkup } from "react-dom/server";

export function renderAppsSdkRadioGroup(): string {
  return renderToStaticMarkup(
    <RadioGroup value="llm" onChange={() => undefined} aria-label="Agent 类型">
      <RadioGroup.Item value="llm">LLM</RadioGroup.Item>
      <RadioGroup.Item value="sequential">顺序</RadioGroup.Item>
    </RadioGroup>,
  );
}
