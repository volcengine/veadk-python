import { Header } from "../../components/composites/Header";
import "./HeaderPreview.css";

export function HeaderPreview() {
  return (
    <section aria-labelledby="header-preview-title">
      <h2 id="header-preview-title" className="component-preview-title">Header</h2>
      <div className="header-preview-specimen">
        <Header
          title="DocuMind"
          description="Parses multi-format docs, extracts key points and to-dos, and skips page-by-page reading."
        />
      </div>
    </section>
  );
}
