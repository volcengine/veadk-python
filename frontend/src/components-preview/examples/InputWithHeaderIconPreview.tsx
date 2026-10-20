import { useState } from "react";
import { InputWithHeaderIcon } from "../../components/primitives/InputWithHeaderIcon";


export function InputWithHeaderIconPreview() {
  const [value, setValue] = useState("");

  return <section aria-labelledby="input-with-header-icon-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="input-with-header-icon-preview-title" className="component-preview-title">Leading Icon</h2>
    <InputWithHeaderIcon
      aria-label="Search"
      placeholder="Search"
      value={value}
      onChange={event => setValue(event.target.value)}
    />
  </section>;
}
