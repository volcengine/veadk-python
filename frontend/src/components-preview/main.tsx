import "../components/tokens";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { applyPreviewTheme, readPreviewTheme } from "./theme";
import { ComponentsPreview } from "./ComponentsPreview";

applyPreviewTheme(readPreviewTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ComponentsPreview />
  </StrictMode>,
);
