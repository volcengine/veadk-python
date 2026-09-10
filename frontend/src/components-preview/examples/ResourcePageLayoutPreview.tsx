import { useState } from "react";
import { ResourcePageLayout } from "../../components/layouts/ResourcePageLayout";
import { ResourceCard } from "../../components/composites/ResourceCard";
import { FilterTabs } from "../../components/primitives/FilterTabs";
import { Button } from "../../components/primitives/Button";
import imgImage1636404790 from "../../components/layouts/ResourcePageLayout/assets/imgImage1636404790.png";
import imgImage1636404101 from "../../components/layouts/ResourcePageLayout/assets/imgImage1636404101.png";
import imgImage1636404793 from "../../components/layouts/ResourcePageLayout/assets/imgImage1636404793.png";
import imgImage1636404792 from "../../components/layouts/ResourcePageLayout/assets/imgImage1636404792.png";
import imgImage1636404795 from "../../components/layouts/ResourcePageLayout/assets/imgImage1636404795.png";
import imgImage1636404794 from "../../components/layouts/ResourcePageLayout/assets/imgImage1636404794.png";
import imgAdd from "../../components/layouts/ResourcePageLayout/assets/imgAdd.svg";
import imgFrame2147240405 from "../../components/layouts/ResourcePageLayout/assets/imgFrame2147240405.svg";
import imgFrame from "../../components/layouts/ResourcePageLayout/assets/imgFrame.svg";
import imgFrame1 from "../../components/layouts/ResourcePageLayout/assets/imgFrame1.svg";
import imgGroup2147240411 from "../../components/layouts/ResourcePageLayout/assets/imgGroup2147240411.svg";
import imgSearchNormal from "../../components/layouts/ResourcePageLayout/assets/imgSearchNormal.svg";
import imgIconPlus from "../../components/layouts/ResourcePageLayout/assets/imgIconPlus.svg";
import imgPixelAvatar from "../../components/layouts/ResourcePageLayout/assets/imgPixelAvatar.svg";
import imgPixelAvatar1 from "../../components/layouts/ResourcePageLayout/assets/imgPixelAvatar1.svg";
import imgPixelAvatar2 from "../../components/layouts/ResourcePageLayout/assets/imgPixelAvatar2.svg";
import imgPixelAvatar3 from "../../components/layouts/ResourcePageLayout/assets/imgPixelAvatar3.svg";
import imgPixelAvatar4 from "../../components/layouts/ResourcePageLayout/assets/imgPixelAvatar4.svg";
import imgPixelAvatar5 from "../../components/layouts/ResourcePageLayout/assets/imgPixelAvatar5.svg";
import imgPixelAvatar6 from "../../components/layouts/ResourcePageLayout/assets/imgPixelAvatar6.svg";
import imgPixelAvatar7 from "../../components/layouts/ResourcePageLayout/assets/imgPixelAvatar7.svg";
import "./ResourcePageLayoutPreview.css";

const meetingDescription = "MeetIntel gathers related project docs, past notes, and collaboration context into a meeting brief.";
const briefDescription = "BriefMate organizes task progress, pending decisions, and attendee needs before the meeting.";
const syncDescription = "Syncs to-do progress across platforms, ranks priorities, and tracks the full project workflow.";
const resources = [
  { title: "GearSync", description: "Gathers related project docs and builds a pre-meeting brief so you show up fully prepared.", background: imgImage1636404101, letter: imgPixelAvatar, avatarClass: "gear", tag: "Codex", draft: true },
  { title: "DocuMind", description: "Parses multi-format docs, extracts key points and to-dos, and skips page-by-page reading.", background: imgImage1636404793, letter: imgPixelAvatar1, avatarClass: "flipped", draft: true },
  { title: "QueryBot", description: "Syncs metrics across business lines in real time, builds visual reports, and flags anomalies fast.", background: imgImage1636404792, letter: imgPixelAvatar2, avatarClass: "query" },
  { title: "SupportHub", description: meetingDescription, background: imgImage1636404795, letter: imgPixelAvatar3, avatarClass: "support", tag: "OpenClaw" },
  { title: "CodeWiz", description: briefDescription, background: imgImage1636404794, letter: imgPixelAvatar4, avatarClass: "default" },
  { title: "AccuFlow", description: syncDescription, background: imgImage1636404793, letter: imgPixelAvatar5, avatarClass: "flipped" },
  { title: "NoteAgent", description: syncDescription, background: imgImage1636404792, letter: imgPixelAvatar6, avatarClass: "large" },
  { title: "TaskFlow", description: meetingDescription, background: imgImage1636404793, letter: imgPixelAvatar7, avatarClass: "flipped" },
  { title: "AutoAgent", description: briefDescription, background: imgImage1636404794, letter: imgPixelAvatar5, avatarClass: "default" },
];

function ResourceBanner() {
  return (
    <div className="resource-page-preview-banner">
      <div className="resource-page-preview-banner__background"><img src={imgImage1636404790} alt="" /></div>
      <div className="resource-page-preview-banner__copy">
        <h3>Create Codex Agent</h3>
        <p>Code generation, bug fixing, logic analysis, and productivity</p>
        <Button className="resource-page-preview-banner__button" startIcon={<img src={imgAdd} alt="" />}>Create Now</Button>
      </div>
      <img className="resource-page-preview-banner__agent" src={imgFrame2147240405} alt="" />
      <span className="resource-page-preview-banner__agent-label">Codex Agent</span>
      <div className="resource-page-preview-banner__decoration resource-page-preview-banner__decoration--left"><img src={imgFrame} alt="" /></div>
      <div className="resource-page-preview-banner__decoration resource-page-preview-banner__decoration--right"><img src={imgFrame1} alt="" /></div>
      <img className="resource-page-preview-banner__branches" src={imgGroup2147240411} alt="" />
    </div>
  );
}

export function ResourcePageLayoutPreview() {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const matchingResources = resources.filter((resource) => `${resource.title} ${resource.description}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <ResourcePageLayout
      title="Agents"
      banner={<ResourceBanner />}
      filters={<FilterTabs aria-label="Resource owner" options={[{ value: "all", label: "All" }, { value: "mine", label: "Created by me" }]} value={filter} onValueChange={setFilter} />}
      actions={<>
        <label className="resource-page-preview-search"><img src={imgSearchNormal} alt="" /><input aria-label="Search agents" placeholder="Search" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <Button className="resource-page-preview-create" startIcon={<img src={imgIconPlus} alt="" />}>Create agent</Button>
      </>}
    >
      {matchingResources.map((resource) => (
        <div className="resource-page-preview-card" key={resource.title}>
          <ResourceCard title={resource.title} description={resource.description} author="Zhou Ran" updatedLabel="Updated 08-12" avatar={<>
            <div className={`resource-page-preview-avatar resource-page-preview-avatar--${resource.avatarClass}`}><img src={resource.background} alt="" /><span /></div>
            <img className="resource-page-preview-avatar-letter" src={resource.letter} alt="" />
          </>} />
          {resource.tag ? <span className={`resource-page-preview-tag resource-page-preview-tag--${resource.title.toLowerCase()}`}>{resource.tag}</span> : null}
          {resource.draft ? <span className="resource-page-preview-draft">draft</span> : null}
        </div>
      ))}
    </ResourcePageLayout>
  );
}
