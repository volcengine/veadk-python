import { useState } from "react";
import { InputWithHeaderIcon } from "../../components/primitives/InputWithHeaderIcon";
import { ComponentApi } from "../api/ComponentApi";

export function InputWithHeaderIconPreview() {
  const [value, setValue] = useState("");

  return <section aria-labelledby="input-with-header-icon-preview-title">
    <h2 id="input-with-header-icon-preview-title" className="component-preview-title">Input with header icon</h2>
    <InputWithHeaderIcon
      aria-label="Search"
      placeholder="Search"
      value={value}
      onChange={event => setValue(event.target.value)}
    />
    <ComponentApi names={["InputWithHeaderIcon"]} />
  </section>;
}
