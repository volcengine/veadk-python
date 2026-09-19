import { ResourceCard } from "../../components/composites/ResourceCard";
import "./ResourceCardPreview.css";

export function ResourceCardPreview() {
  const id = "preview-resource-card";
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 data-preview-heading tabIndex={-1} id={`${id}-title`} className="component-preview-title">Resource Card</h2>
      <div className="resource-card-preview-example">
        <ResourceCard
          title="AutoAgent"
          description="BriefMate organizes task progress, pending decisions, and attendee needs before the meeting."
          author="Zhou Ran"
          updatedLabel="Updated 08-12"
        />
      </div>
    </section>
  );
}
