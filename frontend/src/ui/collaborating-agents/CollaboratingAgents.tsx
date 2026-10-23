import { A2ACenter } from "./A2ACenter";
import "./CollaboratingAgents.css";

export function CollaboratorManager(target: {
  runtimeId: string;
  region: string;
}) {
  return <A2ACenter key={`${target.runtimeId}:${target.region}`} {...target} />;
}
