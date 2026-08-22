import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import dagre from "@dagrejs/dagre";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getViewportForBounds,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Members } from "@openai/apps-sdk-ui/components/Icon";
import layoutIcon from "./assets/create-workspace/layout.svg";
import maximizeIcon from "./assets/create-workspace/maximize.svg";
import zoomInIcon from "./assets/create-workspace/zoom-in.svg";
import zoomOutIcon from "./assets/create-workspace/zoom-out.svg";
import { resolvedModelSource } from "./modelSource";
import type { AgentDraft } from "./types";
import "@xyflow/react/dist/style.css";
import "./CreationFlowCanvas.css";

const TERMINAL_WIDTH = 134;
const TERMINAL_HEIGHT = 60;
const AGENT_WIDTH = 216;
const AGENT_HEIGHT = 141;
const DEBUG_AGENT_WIDTH = 214;
const DEBUG_AGENT_HEIGHT = 137;
const RANK_GAP = 56;
const NODE_GAP = 32;
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 1;
const VIEWPORT_TOP_SAFE_AREA = 24;
const VIEWPORT_SIDE_SAFE_AREA = 28;
const VIEWPORT_BOTTOM_SAFE_AREA = 86;
const FIGMA_VIEWPORT_OFFSET_X = 2;
const FIGMA_VIEWPORT_OFFSET_Y = -1;
const DEBUG_COMPARISON_GRAPH_CENTER_Y = 381.5;
const VIEWPORT_PADDING = {
  top: `${VIEWPORT_TOP_SAFE_AREA}px`,
  right: `${VIEWPORT_SIDE_SAFE_AREA}px`,
  bottom: `${VIEWPORT_BOTTOM_SAFE_AREA}px`,
  left: `${VIEWPORT_SIDE_SAFE_AREA}px`,
} as const;
const CENTERED_VIEWPORT_PADDING = {
  top: `${VIEWPORT_SIDE_SAFE_AREA}px`,
  right: `${VIEWPORT_SIDE_SAFE_AREA}px`,
  bottom: `${VIEWPORT_SIDE_SAFE_AREA}px`,
  left: `${VIEWPORT_SIDE_SAFE_AREA}px`,
} as const;
const DEBUG_COMPARISON_VIEWPORT_PADDING = {
  top: "0px",
  right: "13px",
  bottom: "0px",
  left: "13px",
} as const;

const AGENT_DESCRIPTION =
  "Prepares you for meetings by gathering and summarizing relevant information from your...";

type TerminalData = {
  title: string;
};

type AgentData = {
  title: string;
  description: string;
  systemPrompt: string;
  model: string;
  modelSource: "ark" | "custom";
  modelProvider: string;
  modelApiBase: string;
  tone: "root" | "sub";
  skills: number;
  tools: number;
  subAgents: number;
  comparisonBadge?: string;
};

export interface CreationFlowAgentSelection {
  id: string;
  title: string;
  description: string;
  systemPrompt: string;
  model: string;
  modelSource: "ark" | "custom";
  modelProvider: string;
  modelApiBase: string;
  tone: AgentData["tone"];
}

export type CreationFlowAgentOverrides = Record<
  string,
  Partial<Pick<AgentData, "title" | "description" | "systemPrompt" | "model">>
>;

interface CreationFlowCanvasProps {
  selectedAgentId: string | null;
  configPanelOpen: boolean;
  onAgentSelect: (agent: CreationFlowAgentSelection | null) => void;
  agentOverrides?: CreationFlowAgentOverrides;
  agentDraft?: AgentDraft | null;
  centerViewport?: boolean;
  mode?: "create" | "debug";
  debugComparison?: boolean;
}

type RequestFlowNode = Node<TerminalData, "request">;
type AgentFlowNode = Node<AgentData, "agent">;
type ResponseFlowNode = Node<TerminalData, "response">;
type CreationFlowNode = RequestFlowNode | AgentFlowNode | ResponseFlowNode;

type CreationEdgeData = {
  route: "straight" | "split" | "merge";
};

type CreationFlowEdge = Edge<CreationEdgeData, "insertable">;

type GraphState = {
  nodes: CreationFlowNode[];
  edges: CreationFlowEdge[];
};

const InsertEdgeContext = createContext<(edgeId: string) => void>(() => {});

function RequestIcon() {
  return (
    <svg viewBox="185 19 20 20" aria-hidden="true">
      <path d="M196 23.0667C195.667 23.0667 195.333 23 195 23C194.667 23 194.333 23.0667 194 23.0667M199.867 25.5333C199.469 25.0024 198.998 24.5309 198.467 24.1333M200.933 30C201 29.6667 201 29.3333 201 29C201 28.6667 200.933 28.3333 200.933 28M198.467 33.8666C198.998 33.469 199.469 32.9976 199.867 32.4666M194 34.9333C194.333 34.9999 194.667 34.9999 195 34.9999C195.333 34.9999 195.667 34.9333 196 34.9333M189.333 32.6667L188.333 35.6667L191.333 34.6667M189.067 28C189.067 28.3333 189 28.6667 189 29C189 29.3333 189.067 29.6667 189.067 30M191.533 24.1333C191.002 24.5309 190.531 25.0024 190.133 25.5333" />
    </svg>
  );
}

function ResponseIcon() {
  return (
    <svg viewBox="186 530 20 20" aria-hidden="true">
      <path d="M196 535V531.667H192.667M187.667 540H189.333M193.5 539.167V540.833M198.5 539.167V540.833M202.667 540H204.333M192.667 545L189.333 548.333V536.667C189.333 536.225 189.509 535.801 189.821 535.488C190.134 535.176 190.558 535 191 535H201C201.442 535 201.866 535.176 202.179 535.488C202.491 535.801 202.667 536.225 202.667 536.667V543.333C202.667 543.775 202.491 544.199 202.179 544.512C201.866 544.824 201.442 545 201 545H192.667Z" />
    </svg>
  );
}

function RootAgentIcon() {
  return (
    <svg viewBox="0 0 15 15" aria-hidden="true">
      <path d="M4.125 4.5V5.625M10.875 4.5V5.625M6.75 7.95007C7.35 7.95007 7.875 7.42507 7.875 6.82507V4.5M9.90015 9.89996C8.55015 11.25 6.37515 11.25 5.02515 9.89996M0.750001 4.35V10.65C0.750001 11.9101 0.750001 12.5402 0.995236 13.0215C1.21095 13.4448 1.55516 13.789 1.97852 14.0048C2.45982 14.25 3.08988 14.25 4.35 14.25H10.65C11.9101 14.25 12.5402 14.25 13.0215 14.0048C13.4448 13.7891 13.7891 13.4448 14.0048 13.0215C14.25 12.5402 14.25 11.9101 14.25 10.65V4.35C14.25 3.08988 14.25 2.45982 14.0048 1.97852C13.7891 1.55516 13.4448 1.21095 13.0215 0.995237C12.5402 0.750002 11.9101 0.750002 10.65 0.750001H4.35C3.08988 0.75 2.45982 0.75 1.97852 0.995236C1.55516 1.21095 1.21095 1.55516 0.995236 1.97852C0.750001 2.45982 0.750001 3.08988 0.750001 4.35Z" />
    </svg>
  );
}

function SubAgentIcon() {
  return (
    <svg viewBox="0 0 13.3333 13.3333" aria-hidden="true">
      <path d="M8.66667 10.6667C8.66667 11.7712 9.5621 12.6667 10.6667 12.6667C11.7712 12.6667 12.6667 11.7712 12.6667 10.6667C12.6667 9.5621 11.7712 8.66667 10.6667 8.66667C9.5621 8.66667 8.66667 9.5621 8.66667 10.6667ZM8.66667 10.6667C7.07537 10.6667 5.54924 10.0345 4.42403 8.90931C3.29881 7.78409 2.66667 6.25797 2.66667 4.66667M2.66667 4.66667C3.77124 4.66667 4.66667 3.77124 4.66667 2.66667C4.66667 1.5621 3.77124 0.666667 2.66667 0.666667C1.5621 0.666667 0.666667 1.5621 0.666667 2.66667C0.666667 3.77124 1.5621 4.66667 2.66667 4.66667ZM2.66667 4.66667V12.6667" />
    </svg>
  );
}

function PuzzleIcon() {
  return (
    <svg viewBox="0 0 14 14" aria-hidden="true">
      <path transform="translate(1.3125 1.3125)" d="M8.40023 8.41732V7.52523C8.40023 7.2836 8.5961 7.08773 8.83773 7.08773H9.625C10.1082 7.08773 10.4999 6.69587 10.5 6.21273C10.5 5.72948 10.1083 5.33773 9.625 5.33773H8.83773C8.59618 5.33773 8.40035 5.14175 8.40023 4.90023C8.40023 4.52731 8.39972 4.26925 8.38599 4.06795C8.37252 3.87066 8.34781 3.75968 8.31364 3.67716C8.19819 3.39845 7.97656 3.17681 7.69784 3.06136C7.61532 3.02719 7.50434 3.00248 7.30705 2.98901C7.10575 2.97528 6.84769 2.97477 6.47477 2.97477H5.95011C5.70849 2.97477 5.51261 2.7789 5.51261 2.53727V1.75C5.51261 1.26679 5.12081 0.875062 4.63761 0.875C4.15437 0.875 3.76261 1.26675 3.76261 1.75V2.53727C3.76261 2.77886 3.56669 2.97471 3.32511 2.97477H2.79989C2.42714 2.97477 2.16943 2.97529 1.96818 2.98901C1.77101 3.00247 1.65989 3.02723 1.57739 3.06136C1.29868 3.17681 1.07704 3.39846 0.961589 3.67716C0.92741 3.75968 0.90271 3.87063 0.889242 4.06795C0.881663 4.17904 0.878297 4.30739 0.87671 4.46273H1.22477C2.19127 4.46273 2.97477 5.24623 2.97477 6.21273C2.97465 7.17912 2.1912 7.96273 1.22477 7.96273H0.875001V8.41732C0.875001 8.86558 0.875274 9.17582 0.894939 9.4165C0.91419 9.65198 0.950029 9.78259 0.999187 9.87907C1.10821 10.0929 1.28206 10.2668 1.49593 10.3758C1.59241 10.425 1.72302 10.4608 1.9585 10.4801C2.19918 10.4997 2.50942 10.5 2.95768 10.5H3.15023V10.0186C3.15029 9.12472 3.87472 8.40029 4.76864 8.40023C5.66261 8.40023 6.38755 9.12468 6.38761 10.0186V10.4994C6.79831 10.4993 7.08826 10.4987 7.31616 10.4801C7.55169 10.4608 7.68223 10.425 7.77873 10.3758C7.99272 10.2668 8.16698 10.0931 8.27604 9.87907C8.3252 9.7826 8.36047 9.65196 8.37972 9.4165C8.39939 9.17582 8.40023 8.86558 8.40023 8.41732ZM6.38761 2.09977H6.47477C6.83558 2.09977 7.12835 2.0995 7.36629 2.11572C7.60821 2.13223 7.82588 2.1673 8.0328 2.25301C8.52587 2.45727 8.91774 2.84913 9.12199 3.3422C9.2077 3.54912 9.24277 3.76679 9.25928 4.00871C9.26837 4.14208 9.27126 4.29264 9.27295 4.46273H9.625C10.5915 4.46273 11.375 5.24623 11.375 6.21273C11.3749 7.17912 10.5914 7.96273 9.625 7.96273H9.27523V8.41732C9.27523 8.85114 9.27512 9.20313 9.25187 9.48771C9.2282 9.77729 9.17834 10.0358 9.05591 10.2761C8.86299 10.6548 8.55496 10.9627 8.17635 11.1557C7.93594 11.2782 7.67706 11.3285 7.38737 11.3522C7.10284 11.3754 6.75123 11.375 6.31755 11.375H5.95011C5.70849 11.375 5.51261 11.1791 5.51261 10.9375V10.0186C5.51255 9.60793 5.17936 9.27523 4.76864 9.27523C4.35797 9.27529 4.02529 9.60797 4.02523 10.0186V10.9375C4.02523 11.179 3.82925 11.3749 3.58773 11.375H2.95768C2.52386 11.375 2.17187 11.3755 1.88729 11.3522C1.59766 11.3285 1.33924 11.2781 1.09888 11.1557C0.720201 10.9627 0.412265 10.6548 0.21932 10.2761C0.0968558 10.0358 0.0464585 9.77734 0.0227871 9.48771C-0.00046418 9.20313 6.8722e-07 8.85114 6.8722e-07 8.41732V7.52523C6.8722e-07 7.2836 0.195876 7.08773 0.437501 7.08773H1.22477C1.70795 7.08773 2.09965 6.69587 2.09977 6.21273C2.09977 5.72948 1.70802 5.33773 1.22477 5.33773H0.437501C0.195952 5.33773 0.000123908 5.14175 6.8722e-07 4.90023C6.8722e-07 4.53942 -0.000268731 4.24665 0.0159512 4.00871C0.0324573 3.76679 0.067533 3.54912 0.15324 3.3422C0.357513 2.84915 0.74936 2.45725 1.24243 2.25301C1.44929 2.16735 1.66652 2.13223 1.90837 2.11572C2.14633 2.09949 2.439 2.09977 2.79989 2.09977H2.88761V1.75C2.88761 0.783502 3.67112 0 4.63761 0C5.60406 6.1631e-05 6.38761 0.78354 6.38761 1.75V2.09977Z" />
    </svg>
  );
}

function ToolIcon() {
  return (
    <svg viewBox="0 0 14 14" aria-hidden="true">
      <path transform="translate(1.3125 1.3125)" d="M10.4999 3.73242C10.4999 3.5476 10.4815 3.3671 10.4481 3.19238L9.39706 4.24398C9.29344 4.3476 9.19734 4.44428 9.11052 4.51799C9.01979 4.59501 8.91049 4.67261 8.771 4.71794C8.57294 4.78222 8.35951 4.78227 8.16146 4.71794C8.02205 4.67264 7.91321 4.59497 7.82251 4.51799C7.73571 4.4443 7.63957 4.34757 7.53597 4.24398L7.13094 3.83895C7.02735 3.73536 6.93063 3.63921 6.85694 3.55241C6.77996 3.46171 6.70228 3.35287 6.65699 3.21346C6.59265 3.01542 6.5927 2.80198 6.65699 2.60392C6.70231 2.46443 6.77991 2.35514 6.85694 2.2644C6.93064 2.17758 7.02733 2.08148 7.13094 1.97786L8.18197 0.92627C8.00746 0.892962 7.8271 0.875 7.6425 0.875C6.06456 0.875092 4.78565 2.15446 4.78565 3.73242C4.78566 3.96685 4.81364 4.19432 4.86654 4.41146C4.89833 4.54195 4.92565 4.6528 4.94344 4.74129C4.96012 4.82424 4.97737 4.92781 4.97022 5.03239C4.96004 5.18104 4.93054 5.2869 4.86198 5.41919C4.78358 5.57041 4.64365 5.70304 4.51905 5.82764L1.08798 9.25814C0.80392 9.54219 0.80392 10.0029 1.08798 10.2869C1.37203 10.571 1.83273 10.571 2.11678 10.2869L5.54729 6.85588C5.67188 6.73128 5.80451 6.59134 5.95573 6.51294C6.08803 6.44439 6.19388 6.41488 6.34253 6.4047C6.44711 6.39755 6.55068 6.4148 6.63363 6.43148C6.72213 6.44927 6.83298 6.47659 6.96346 6.50838C7.18061 6.56128 7.40807 6.58926 7.6425 6.58927C9.22046 6.58927 10.4998 5.31036 10.4999 3.73242ZM11.3749 3.73242C11.3748 5.79361 9.70371 7.46427 7.6425 7.46427C7.33778 7.46426 7.04108 7.4276 6.75668 7.35832C6.61866 7.3247 6.52799 7.30285 6.46102 7.28939C6.38857 7.27483 6.38261 7.27878 6.40235 7.27743C6.39004 7.27827 6.38268 7.2792 6.37899 7.2797C6.37547 7.28126 6.369 7.28451 6.35848 7.28996C6.36915 7.28443 6.36387 7.28461 6.32829 7.31673C6.29157 7.3499 6.2441 7.39694 6.16594 7.4751L2.73544 10.9056C2.10967 11.5314 1.09509 11.5314 0.469323 10.9056C-0.156441 10.2798 -0.156441 9.26525 0.469323 8.63949L3.89983 5.20898C3.97798 5.13083 4.02503 5.08335 4.05819 5.04663C4.09031 5.01106 4.09049 5.00577 4.08496 5.01644C4.09041 5.00593 4.09366 4.99946 4.09522 4.99593C4.09572 4.99224 4.09665 4.98489 4.0975 4.97258C4.09615 4.99231 4.1001 4.98635 4.08553 4.9139C4.07207 4.84693 4.05023 4.75626 4.01661 4.61825C3.94733 4.33384 3.91066 4.03715 3.91065 3.73242C3.91065 1.67121 5.58131 9.19966e-05 7.6425 0C8.18923 0 8.70982 0.117759 9.17888 0.329834C9.3097 0.388998 9.40372 0.508748 9.42953 0.649984C9.45529 0.791275 9.40973 0.936357 9.30819 1.03792L7.7496 2.59652C7.6358 2.71032 7.56922 2.77741 7.52401 2.83065C7.48212 2.87999 7.48468 2.88806 7.48926 2.87394C7.482 2.89629 7.48205 2.92051 7.48926 2.94287C7.48472 2.92906 7.48244 2.93718 7.52401 2.98617C7.56921 3.0394 7.63582 3.10652 7.7496 3.2203L8.15463 3.62533C8.26841 3.73911 8.33552 3.80572 8.38876 3.85091C8.43774 3.89248 8.44586 3.8902 8.43205 3.88566C8.45441 3.89288 8.47863 3.89292 8.50098 3.88566C8.48687 3.89025 8.49493 3.8928 8.54427 3.85091C8.59752 3.80571 8.66461 3.73912 8.77841 3.62533L10.337 2.06673L10.3769 2.03141C10.4746 1.95501 10.6013 1.92284 10.7249 1.94539C10.8662 1.9712 10.9859 2.06522 11.0451 2.19605C11.2572 2.6651 11.3749 3.18569 11.3749 3.73242Z" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d="M8 3.5v9M3.5 8h9" />
    </svg>
  );
}

function RequestNode({ data }: NodeProps<RequestFlowNode>) {
  return (
    <div className="creation-flow__terminal creation-flow__terminal--request" role="group" aria-label={data.title}>
      <span className="creation-flow__terminal-icon"><RequestIcon /></span>
      <span className="creation-flow__terminal-title">{data.title}</span>
      <Handle type="source" position={Position.Bottom} className="creation-flow__port" />
    </div>
  );
}

function ResponseNode({ data }: NodeProps<ResponseFlowNode>) {
  return (
    <div className="creation-flow__terminal creation-flow__terminal--response" role="group" aria-label={data.title}>
      <Handle type="target" position={Position.Top} className="creation-flow__port creation-flow__port--hidden" />
      <span className="creation-flow__terminal-icon"><ResponseIcon /></span>
      <span className="creation-flow__terminal-title">{data.title}</span>
    </div>
  );
}

function AgentNode({ data, selected }: NodeProps<AgentFlowNode>) {
  const AgentIcon = data.tone === "root" ? RootAgentIcon : SubAgentIcon;
  return (
    <article
      className={`creation-flow__agent creation-flow__agent--${data.tone}${selected ? " is-selected" : ""}`}
      aria-label={`${data.title} 智能体`}
    >
      <Handle type="target" position={Position.Top} className="creation-flow__port creation-flow__port--hidden" />
      <header className="creation-flow__agent-header">
        <span className="creation-flow__agent-icon"><AgentIcon /></span>
        <span className="creation-flow__agent-title">{data.title}</span>
        {data.comparisonBadge && (
          <span className="creation-flow__agent-comparison-badge">{data.comparisonBadge}</span>
        )}
      </header>
      <p className="creation-flow__agent-description">{data.description}</p>
      <div className="creation-flow__agent-meta" aria-label="智能体能力数量">
        <span><PuzzleIcon /><span className="creation-flow__agent-meta-count">{data.skills}</span></span>
        <span><ToolIcon /><span className="creation-flow__agent-meta-count">{data.tools}</span></span>
        <span><Members aria-hidden="true" /><span className="creation-flow__agent-meta-count">{data.subAgents}</span></span>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className={`creation-flow__port${data.tone === "root" ? " creation-flow__port--hidden" : ""}`}
      />
    </article>
  );
}

const nodeTypes = {
  request: RequestNode,
  agent: AgentNode,
  response: ResponseNode,
};

function edgeGeometry(
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
  route: CreationEdgeData["route"],
) {
  if (route === "straight" || Math.abs(sourceX - targetX) < 0.5) {
    return {
      path: `M ${sourceX} ${sourceY} V ${targetY - 1}`,
      labelX: sourceX,
      labelY: (sourceY + targetY) / 2,
    };
  }

  const direction = targetX > sourceX ? 1 : -1;
  const bendY = route === "split"
    ? (sourceY + targetY) / 2 - 1.286
    : (sourceY + targetY) / 2 + 2.257;
  const radius = Math.min(16, Math.abs(targetX - sourceX) / 2);
  const path = [
    `M ${sourceX} ${sourceY}`,
    `V ${bendY - radius}`,
    `Q ${sourceX} ${bendY} ${sourceX + direction * radius} ${bendY}`,
    `H ${targetX - direction * radius}`,
    `Q ${targetX} ${bendY} ${targetX} ${bendY + radius}`,
    `V ${targetY - 1}`,
  ].join(" ");
  return {
    path,
    labelX: (sourceX + targetX) / 2,
    labelY: bendY,
  };
}

function InsertableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps<CreationFlowEdge>) {
  const onInsert = useContext(InsertEdgeContext);
  const [hovered, setHovered] = useState(false);
  const geometry = edgeGeometry(
    sourceX,
    sourceY,
    targetX,
    targetY,
    data?.route ?? "straight",
  );
  const arrowPath = `M ${targetX - 3.5} ${targetY - 4.5} L ${targetX} ${targetY - 1} L ${targetX + 3.5} ${targetY - 4.5}`;

  return (
    <>
      <BaseEdge id={id} path={geometry.path} className="creation-flow__edge-visible" />
      <path d={arrowPath} className="creation-flow__edge-arrow" />
      <path
        d={geometry.path}
        className="creation-flow__edge-hit"
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
      />
      <EdgeLabelRenderer>
        <div
          className={`creation-flow__edge-tool${hovered ? " is-visible" : ""}`}
          style={{
            transform: `translate(-50%, -50%) translate(${geometry.labelX}px, ${geometry.labelY}px)`,
          }}
          onPointerEnter={() => setHovered(true)}
          onPointerLeave={() => setHovered(false)}
        >
          <button
            type="button"
            className="creation-flow__edge-add nodrag nopan"
            aria-label="在此处新增智能体"
            title="在此处新增智能体"
            onClick={(event) => {
              event.stopPropagation();
              onInsert(id);
            }}
          >
            <PlusIcon />
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const edgeTypes = {
  insertable: InsertableEdge,
};

function initialGraph(): GraphState {
  const nodes: CreationFlowNode[] = [
    {
      id: "request",
      type: "request",
      position: { x: 0, y: 0 },
      data: { title: "用户请求" },
      draggable: false,
      selectable: false,
    },
    {
      id: "meeting-assistant",
      type: "agent",
      position: { x: 0, y: 0 },
      data: {
        title: "Meeting Assistant",
        description: AGENT_DESCRIPTION,
        systemPrompt: "",
        model: "doubao-seed-2.0-lite",
        modelSource: "ark",
        modelProvider: "",
        modelApiBase: "",
        tone: "root",
        skills: 2,
        tools: 2,
        subAgents: 2,
      },
      draggable: false,
      selectable: true,
    },
    ...["sub-agent-left", "sub-agent-right"].map<AgentFlowNode>((id) => ({
      id,
      type: "agent",
      position: { x: 0, y: 0 },
      data: {
        title: "SubAgent1",
        description: AGENT_DESCRIPTION,
        systemPrompt: "",
        model: "doubao-seed-2.0-lite",
        modelSource: "ark",
        modelProvider: "",
        modelApiBase: "",
        tone: "sub",
        skills: 2,
        tools: 2,
        subAgents: 0,
      },
      draggable: false,
      selectable: true,
    })),
    {
      id: "response",
      type: "response",
      position: { x: 0, y: 0 },
      data: { title: "最终回复" },
      draggable: false,
      selectable: false,
    },
  ];

  const edges: CreationFlowEdge[] = [
    makeEdge("request", "meeting-assistant", "straight"),
    makeEdge("meeting-assistant", "sub-agent-left", "split"),
    makeEdge("meeting-assistant", "sub-agent-right", "split"),
    makeEdge("sub-agent-left", "response", "merge"),
    makeEdge("sub-agent-right", "response", "merge"),
  ];
  return { nodes, edges };
}

function countAgentSkills(agent: AgentDraft) {
  return new Set([
    ...agent.skills,
    ...(agent.selectedSkills ?? []).map((skill) => skill.slug || skill.name),
  ]).size;
}

function countAgentTools(agent: AgentDraft) {
  return new Set([
    ...agent.tools,
    ...(agent.builtinTools ?? []),
    ...(agent.customTools ?? []).map((tool) => tool.name),
    ...(agent.mcpTools ?? []).map((tool) => tool.name),
  ]).size;
}

function graphFromDraft(draft: AgentDraft): GraphState {
  const nodes: CreationFlowNode[] = [
    {
      id: "request",
      type: "request",
      position: { x: 0, y: 0 },
      data: { title: "用户请求" },
      draggable: false,
      selectable: false,
    },
  ];
  const edges: CreationFlowEdge[] = [];
  const leafIds: string[] = [];

  const visit = (
    agent: AgentDraft,
    path: number[],
    parentId: string,
    siblingCount: number,
  ) => {
    const id = path.length === 0 ? "agent-root" : `agent-${path.join("-")}`;
    nodes.push({
      id,
      type: "agent",
      position: { x: 0, y: 0 },
      data: {
        title: agent.name || (path.length === 0 ? "Agent" : "SubAgent"),
        description: agent.description,
        systemPrompt: agent.instruction,
        model: agent.modelName || agent.model || "doubao-seed-2.0-lite",
        modelSource: resolvedModelSource(
          agent,
          agent.cloudProvider ?? draft.cloudProvider ?? "volcengine",
        ),
        modelProvider: agent.modelProvider ?? "",
        modelApiBase: agent.modelApiBase ?? "",
        tone: path.length === 0 ? "root" : "sub",
        skills: countAgentSkills(agent),
        tools: countAgentTools(agent),
        subAgents: agent.subAgents.length,
      },
      draggable: false,
      selectable: true,
    });
    edges.push(
      makeEdge(parentId, id, siblingCount > 1 ? "split" : "straight"),
    );

    if (agent.subAgents.length === 0) {
      leafIds.push(id);
      return;
    }
    agent.subAgents.forEach((child, index) => {
      visit(child, [...path, index], id, agent.subAgents.length);
    });
  };

  visit(draft, [], "request", 1);
  nodes.push({
    id: "response",
    type: "response",
    position: { x: 0, y: 0 },
    data: { title: "最终回复" },
    draggable: false,
    selectable: false,
  });
  leafIds.forEach((leafId) => {
    edges.push(
      makeEdge(leafId, "response", leafIds.length > 1 ? "merge" : "straight"),
    );
  });
  return { nodes, edges };
}

function makeEdge(
  source: string,
  target: string,
  route: CreationEdgeData["route"],
): CreationFlowEdge {
  return {
    id: `${source}-${target}`,
    source,
    target,
    type: "insertable",
    data: { route },
    selectable: false,
    focusable: false,
  };
}

function nodeSize(node: CreationFlowNode, mode: "create" | "debug") {
  return node.type === "agent"
    ? mode === "debug"
      ? { width: DEBUG_AGENT_WIDTH, height: DEBUG_AGENT_HEIGHT }
      : { width: AGENT_WIDTH, height: AGENT_HEIGHT }
    : { width: TERMINAL_WIDTH, height: TERMINAL_HEIGHT };
}

function graphBounds(nodes: CreationFlowNode[], mode: "create" | "debug") {
  if (nodes.length === 0) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }

  const left = Math.min(...nodes.map((node) => node.position.x));
  const top = Math.min(...nodes.map((node) => node.position.y));
  const right = Math.max(...nodes.map((node) => {
    const size = nodeSize(node, mode);
    return node.position.x + size.width;
  }));
  const bottom = Math.max(...nodes.map((node) => {
    const size = nodeSize(node, mode);
    return node.position.y + size.height;
  }));

  return {
    x: left,
    y: top,
    width: right - left,
    height: bottom - top,
  };
}

function layoutGraph(state: GraphState, mode: "create" | "debug"): GraphState {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "TB",
    ranksep: RANK_GAP,
    nodesep: NODE_GAP,
    marginx: 0,
    marginy: 0,
  });
  state.nodes.forEach((node) => graph.setNode(node.id, nodeSize(node, mode)));
  state.edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);
  return {
    edges: state.edges,
    nodes: state.nodes.map((node) => {
      const position = graph.node(node.id) as { x: number; y: number };
      const size = nodeSize(node, mode);
      return {
        ...node,
        position: {
          x: position.x - size.width / 2,
          y: position.y - size.height / 2,
        },
      };
    }),
  };
}

function CreationFlowCanvasInner({
  selectedAgentId,
  configPanelOpen,
  onAgentSelect,
  agentOverrides = {},
  agentDraft = null,
  centerViewport = false,
  mode = "create",
  debugComparison = false,
}: CreationFlowCanvasProps) {
  const [graph, setGraph] = useState<GraphState>(() =>
    agentDraft ? graphFromDraft(agentDraft) : initialGraph(),
  );
  const sequence = useRef(2);
  const canvasRef = useRef<HTMLDivElement>(null);
  const viewportWasAutoFit = useRef(true);

  useEffect(() => {
    setGraph(agentDraft ? graphFromDraft(agentDraft) : initialGraph());
    viewportWasAutoFit.current = true;
  }, [agentDraft]);
  const layout = useMemo(() => layoutGraph(graph, mode), [graph, mode]);
  const layoutBounds = useMemo(() => graphBounds(layout.nodes, mode), [layout.nodes, mode]);
  const layoutBoundsRef = useRef(layoutBounds);
  layoutBoundsRef.current = layoutBounds;
  const layoutSignature = useMemo(() => [
    ...graph.nodes.map((node) => node.id),
    ...graph.edges.map((edge) => `${edge.source}>${edge.target}`),
  ].join("|"), [graph.edges, graph.nodes]);
  const rootAgentId = agentDraft ? "agent-root" : "meeting-assistant";
  const laidOutGraph = useMemo<GraphState>(() => {
    return {
      ...layout,
      nodes: layout.nodes.map<CreationFlowNode>((node) => {
        const selected = node.id === selectedAgentId;

        if (node.type !== "agent") {
          return { ...node, selected };
        }

        const data = { ...node.data, ...agentOverrides[node.id] };

        if (debugComparison && node.id === rootAgentId) {
          return {
            ...node,
            selected,
            data: { ...data, comparisonBadge: "B·2" },
          };
        }

        return { ...node, selected, data };
      }),
    };
  }, [agentOverrides, debugComparison, layout, rootAgentId, selectedAgentId]);
  const {
    getViewport,
    setViewport,
    zoomIn,
    zoomOut,
  } = useReactFlow<CreationFlowNode, CreationFlowEdge>();

  const fitCanvas = useCallback(async (duration = 180) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const { width, height } = canvas.getBoundingClientRect();
    if (width <= 0 || height <= 0) return;

    const viewport = getViewportForBounds(
      layoutBoundsRef.current,
      width,
      height,
      MIN_ZOOM,
      MAX_ZOOM,
      debugComparison
        ? DEBUG_COMPARISON_VIEWPORT_PADDING
        : centerViewport
          ? CENTERED_VIEWPORT_PADDING
          : VIEWPORT_PADDING,
    );
    if (debugComparison) {
      const bounds = layoutBoundsRef.current;
      viewport.x = width / 2 - (bounds.x + bounds.width / 2) * viewport.zoom;
      viewport.y = DEBUG_COMPARISON_GRAPH_CENTER_Y
        - (bounds.y + bounds.height / 2) * viewport.zoom;
    } else if (!centerViewport) {
      viewport.x += mode === "debug" ? FIGMA_VIEWPORT_OFFSET_X + 4 : FIGMA_VIEWPORT_OFFSET_X;
      viewport.y += mode === "debug" ? FIGMA_VIEWPORT_OFFSET_Y + 4 : FIGMA_VIEWPORT_OFFSET_Y;
    }
    viewportWasAutoFit.current = true;
    await setViewport(viewport, { duration });
  }, [centerViewport, debugComparison, mode, setViewport]);

  const graphIsInsideSafeArea = useCallback((width: number, height: number) => {
    const bounds = layoutBoundsRef.current;
    const viewport = getViewport();
    const left = bounds.x * viewport.zoom + viewport.x;
    const top = bounds.y * viewport.zoom + viewport.y;
    const right = (bounds.x + bounds.width) * viewport.zoom + viewport.x;
    const bottom = (bounds.y + bounds.height) * viewport.zoom + viewport.y;

    return left >= VIEWPORT_SIDE_SAFE_AREA
      && top >= VIEWPORT_TOP_SAFE_AREA
      && right <= width - VIEWPORT_SIDE_SAFE_AREA
      && bottom <= height - VIEWPORT_BOTTOM_SAFE_AREA;
  }, [getViewport]);

  const insertAgent = useCallback((edgeId: string) => {
    setGraph((current) => {
      const edge = current.edges.find((candidate) => candidate.id === edgeId);
      if (!edge) return current;
      sequence.current += 1;
      const id = `sub-agent-${sequence.current}`;
      const node: AgentFlowNode = {
        id,
        type: "agent",
        position: { x: 0, y: 0 },
        data: {
          title: `SubAgent${sequence.current}`,
          description: AGENT_DESCRIPTION,
          systemPrompt: "",
          model: "doubao-seed-2.0-lite",
          modelSource: "ark",
          modelProvider: "",
          modelApiBase: "",
          tone: "sub",
          skills: 2,
          tools: 2,
          subAgents: 0,
        },
        draggable: false,
        selectable: true,
      };
      const route = edge.data?.route ?? "straight";
      const firstRoute = route === "split" ? "split" : "straight";
      const secondRoute = route === "merge" ? "merge" : "straight";
      return {
        nodes: [...current.nodes, node],
        edges: [
          ...current.edges.filter((candidate) => candidate.id !== edgeId),
          makeEdge(edge.source, id, firstRoute),
          makeEdge(id, edge.target, secondRoute),
        ],
      };
    });
  }, []);

  useEffect(() => {
    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        void fitCanvas();
      });
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
  }, [fitCanvas, layoutSignature]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let frame = 0;
    let previousWidth = canvas.clientWidth;
    let previousHeight = canvas.clientHeight;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;

      const { width, height } = entry.contentRect;
      if (Math.abs(width - previousWidth) < 1 && Math.abs(height - previousHeight) < 1) {
        return;
      }
      previousWidth = width;
      previousHeight = height;
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        if (viewportWasAutoFit.current || !graphIsInsideSafeArea(width, height)) {
          void fitCanvas(0);
        }
      });
    });
    observer.observe(canvas);

    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame);
    };
  }, [fitCanvas, graphIsInsideSafeArea]);

  return (
    <InsertEdgeContext.Provider value={mode === "debug" ? () => {} : insertAgent}>
      <div
        ref={canvasRef}
        className={`creation-flow creation-flow--${mode}${debugComparison ? " creation-flow--debug-comparison" : ""}${configPanelOpen ? " creation-flow--config-open" : ""}`}
        aria-label="智能体结构画布"
      >
        <ReactFlow<CreationFlowNode, CreationFlowEdge>
          nodes={laidOutGraph.nodes}
          edges={laidOutGraph.edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          minZoom={MIN_ZOOM}
          maxZoom={MAX_ZOOM}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          panOnDrag
          zoomOnDoubleClick={false}
          onMoveStart={(event) => {
            if (event) viewportWasAutoFit.current = false;
          }}
          onNodeClick={(_event, node) => {
            if (node.type !== "agent") {
              if (mode !== "debug") onAgentSelect(null);
              return;
            }
            onAgentSelect({
              id: node.id,
              title: node.data.title,
              description: node.data.description,
              systemPrompt: node.data.systemPrompt,
              model: node.data.model,
              modelSource: node.data.modelSource,
              modelProvider: node.data.modelProvider,
              modelApiBase: node.data.modelApiBase,
              tone: node.data.tone,
            });
          }}
          onPaneClick={() => {
            if (mode !== "debug") onAgentSelect(null);
          }}
          proOptions={{ hideAttribution: true }}
        />

        {mode === "create" && <div className="creation-flow__canvas-actions" aria-label="画布工具">
          <div className="creation-flow__zoom-actions">
            <button type="button" className="creation-flow__canvas-action" aria-label="放大" onClick={() => {
              viewportWasAutoFit.current = false;
              void zoomIn({ duration: 160 });
            }}>
              <img src={zoomInIcon} alt="" />
            </button>
            <button type="button" className="creation-flow__canvas-action" aria-label="缩小" onClick={() => {
              viewportWasAutoFit.current = false;
              void zoomOut({ duration: 160 });
            }}>
              <img src={zoomOutIcon} alt="" />
            </button>
          </div>
          <button
            type="button"
            className="creation-flow__canvas-action"
            aria-label="适应画布"
            onClick={() => void fitCanvas()}
          >
            <img src={maximizeIcon} alt="" />
          </button>
          <button
            type="button"
            className="creation-flow__canvas-action creation-flow__layout-action"
            aria-label="恢复纵向布局"
            onClick={() => void fitCanvas()}
          >
            <img src={layoutIcon} alt="" />
          </button>
        </div>}
      </div>
    </InsertEdgeContext.Provider>
  );
}

export function CreationFlowCanvas(props: CreationFlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <CreationFlowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
