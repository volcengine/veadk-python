import { ComponentApi } from "../api/ComponentApi";
import { AgentNode } from "../../components/nodes/AgentNode";
import "./AgentNodePreview.css";

export function AgentNodePreview() {
  return <section aria-labelledby="agent-node-preview-title"><h2 className="component-preview-title" id="agent-node-preview-title">Agent node</h2><div className="agent-node-preview-examples">
    <section aria-labelledby="agent-node-selected-title"><h3 id="agent-node-selected-title">Selected</h3><AgentNode selected iconVariant="agent" title="Meeting Assistant" description="Prepares you for meetings by gathering and summarizing relevant information from your..." skillCount={2} toolCount={3} /></section>
    <section aria-labelledby="agent-node-default-title"><h3 id="agent-node-default-title">Default</h3><AgentNode title="Assistant" description="Turns research into a concise briefing with key points, questions, and action items." skillCount={1} toolCount={3} /></section>
  </div><ComponentApi names={["AgentNode"]} />
    </section>;
}
