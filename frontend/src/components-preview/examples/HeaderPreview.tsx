import { Header } from "../../components/composites/Header";
import { ScrollArea } from "../../components/primitives/ScrollArea";
import "./HeaderPreview.css";

export function HeaderPreview() {
  return (
    <section aria-labelledby="header-preview-title">
      <h2 data-preview-heading tabIndex={-1} id="header-preview-title" className="component-preview-title">Default</h2>
      <ScrollArea className="header-preview-viewport" orientation="horizontal" role="region" aria-label="Header 预览，可横向滚动" tabIndex={0}>
        <div className="header-preview-specimen">
          <Header
            title="DocuMind"
            description="Parses multi-format docs, extracts key points and to-dos, and skips page-by-page reading."
          />
        </div>
      </ScrollArea>
    </section>
  );
}
