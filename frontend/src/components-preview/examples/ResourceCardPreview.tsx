import { useId } from "react";
import { ResourceCard } from "../../components/composites/ResourceCard";
import "./ResourceCardPreview.css";

export function ResourceCardPreview() {
  const id = useId();
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="component-preview-title">Resource card</h2>
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
