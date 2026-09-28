import { InputWithHeaderIconPreview } from "./InputWithHeaderIconPreview";
import { InputWithTailIconPreview } from "./InputWithTailIconPreview";

export function InputPreview() {
  return <div className="components-preview-variants">
    <InputWithHeaderIconPreview />
    <InputWithTailIconPreview />
  </div>;
}
