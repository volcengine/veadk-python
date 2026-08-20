import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type MutableRefObject,
  type RefObject,
  type SVGProps,
} from "react";
import dagre from "@dagrejs/dagre";
import {
  EditorRenderer,
  FreeLayoutEditorProvider,
  LineType,
  WorkflowNodeRenderer,
  useClientContext,
  useNodeRender,
  type FreeLayoutPluginContext,
  type FreeLayoutProps,
  type WorkflowJSON,
  type WorkflowNodeProps,
  type WorkflowNodeRegistry,
} from "@flowgram.ai/free-layout-editor";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import type { AgentDraft } from "./types";
import {
  AgentSkillCountIcon,
  AgentToolCountIcon,
  CanvasAgentTypeIcon,
} from "../ui/CapabilityIcons";
import {
  CreateAddIcon,
  TerminalFinalReplyIcon,
  TerminalUserRequestIcon,
} from "../ui/icons/CreateAgentIcons";
import "@flowgram.ai/free-layout-editor/index.css";
import "./AgentBuildCanvas.css";

type NodePath = number[];
type AgentType = NonNullable<AgentDraft["agentType"]>;

export type CanvasDirection = "horizontal" | "vertical";

type CanvasNodeData = {
  kind: "agent" | "terminal";
  path?: NodePath;
  title: string;
  nameMissing?: boolean;
  pattern?: AgentType;
  modelLabel?: string;
  description?: string;
  toolCount?: number;
  skillCount?: number;
  layoutWidth: number;
  layoutHeight: number;
  terminalKind?: "input" | "output";
};

type FlatAgentNode = {
  id: string;
  path: NodePath;
  agent: AgentDraft;
};

const PATTERN_COPY: Record<AgentType, { label: string }> = {
  llm: { label: "智能体" },
  sequential: { label: "分步协作" },
  parallel: { label: "同时处理" },
  loop: { label: "循环执行" },
  a2a: { label: "远程智能体" },
};

const NODE_WIDTH = 214;
const NODE_HEIGHT = 168;
const COMPACT_NODE_HEIGHT = 138;
const READ_ONLY_NODE_HEIGHT = 133;
const READ_ONLY_COMPACT_NODE_HEIGHT = 104;
const TERMINAL_WIDTH = 120;
const TERMINAL_HEIGHT = 52;
const FIGMA_FLOW_LINE_LENGTH = 69;

function canvasAgentTitle(agent: AgentDraft): string {
  if (agent.agentType === "a2a") return "远程智能体";
  return agent.name.trim() || "名称未配置";
}

function canvasAgentModel(agent: AgentDraft): string {
  return agent.modelName?.trim() || agent.model?.trim() || "模型未配置";
}

function uniqueCapabilityCount(values: Array<string | undefined>): number {
  return new Set(
    values
      .map((value) => value?.trim())
      .filter((value): value is string => !!value),
  ).size;
}

function canvasAgentCardData(agent: AgentDraft) {
  return {
    modelLabel: canvasAgentModel(agent),
    description: agent.description.trim() || "描述未配置",
    toolCount: uniqueCapabilityCount([
      ...agent.tools,
      ...(agent.builtinTools ?? []),
      ...(agent.customTools ?? []).map((tool) => tool.name),
      ...(agent.mcpTools ?? []).map((tool) => tool.name),
    ]),
    skillCount: uniqueCapabilityCount([
      ...agent.skills,
      ...(agent.selectedSkills ?? []).map((skill) => skill.name),
    ]),
  };
}

const showsModelCapabilities = (type: AgentType): boolean => type === "llm";

const nodeHeight = (type: AgentType, readOnly: boolean): number =>
  showsModelCapabilities(type)
    ? readOnly
      ? READ_ONLY_NODE_HEIGHT
      : NODE_HEIGHT
    : readOnly
      ? READ_ONLY_COMPACT_NODE_HEIGHT
      : COMPACT_NODE_HEIGHT;

function pathId(path: NodePath): string {
  return path.length === 0 ? "agent-root" : `agent-${path.join("-")}`;
}

function flattenAgentNodes(
  agent: AgentDraft,
  path: NodePath = [],
  result: FlatAgentNode[] = [],
): FlatAgentNode[] {
  result.push({ id: pathId(path), path, agent });
  agent.subAgents.forEach((child, index) => {
    flattenAgentNodes(child, [...path, index], result);
  });
  return result;
}

function agentNodeData(
  agent: AgentDraft,
  path: NodePath,
  readOnly: boolean,
): CanvasNodeData {
  const type = agent.agentType ?? "llm";
  return {
    kind: "agent",
    path,
    title: canvasAgentTitle(agent),
    ...canvasAgentCardData(agent),
    nameMissing: type !== "a2a" && agent.name.trim().length === 0,
    pattern: type,
    layoutWidth: NODE_WIDTH,
    layoutHeight: nodeHeight(type, readOnly),
  };
}

type WorkflowEdge = WorkflowJSON["edges"][number];

function workflowEdge(sourceNodeID: string, targetNodeID: string): WorkflowEdge {
  return { sourceNodeID, targetNodeID };
}

function buildAgentEdges(
  agent: AgentDraft,
  path: NodePath,
  edges: WorkflowEdge[],
): { entry: string; exits: string[] } {
  const id = pathId(path);
  const children = agent.subAgents.map((child, index) =>
    buildAgentEdges(child, [...path, index], edges),
  );
  if (children.length === 0) return { entry: id, exits: [id] };

  const type = agent.agentType ?? "llm";
  if (type === "parallel") {
    children.forEach((child) => edges.push(workflowEdge(id, child.entry)));
    return { entry: id, exits: children.flatMap((child) => child.exits) };
  }

  edges.push(workflowEdge(id, children[0].entry));
  for (let index = 0; index < children.length - 1; index += 1) {
    children[index].exits.forEach((exit) =>
      edges.push(workflowEdge(exit, children[index + 1].entry)),
    );
  }
  if (type === "loop") {
    const lastChild = children[children.length - 1];
    lastChild.exits.forEach((exit: string) =>
      edges.push(workflowEdge(exit, children[0].entry)),
    );
    return { entry: id, exits: [id] };
  }
  return { entry: id, exits: children[children.length - 1].exits };
}

function layoutWorkflow(
  nodes: WorkflowJSON["nodes"],
  edges: WorkflowEdge[],
  direction: CanvasDirection,
): WorkflowJSON["nodes"] {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: direction === "vertical" ? "TB" : "LR",
    ranksep: FIGMA_FLOW_LINE_LENGTH,
    nodesep: 40,
    edgesep: 16,
    marginx: 24,
    marginy: 24,
  });
  nodes.forEach((node) => {
    const data = node.data as CanvasNodeData;
    graph.setNode(node.id, {
      width: data.layoutWidth,
      height: data.layoutHeight,
    });
  });
  edges.forEach((edge) => graph.setEdge(edge.sourceNodeID, edge.targetNodeID));
  dagre.layout(graph);
  return nodes.map((node) => {
    const data = node.data as CanvasNodeData;
    const position = graph.node(node.id) as { x: number; y: number };
    return {
      ...node,
      meta: {
        ...node.meta,
        position: {
          x: position.x - data.layoutWidth / 2,
          y: position.y - data.layoutHeight / 2,
        },
      },
    };
  });
}

function buildFlowgramWorkflow(
  draft: AgentDraft,
  direction: CanvasDirection,
  readOnly: boolean,
): WorkflowJSON {
  const flatAgents = flattenAgentNodes(draft);
  const edges: WorkflowEdge[] = [];
  const rootFlow = buildAgentEdges(draft, [], edges);
  edges.unshift(workflowEdge("terminal-input", rootFlow.entry));
  rootFlow.exits.forEach((exit) =>
    edges.push(workflowEdge(exit, "terminal-output")),
  );

  const nodes: WorkflowJSON["nodes"] = [
    {
      id: "terminal-input",
      type: "terminal-input",
      meta: { position: { x: 0, y: 0 } },
      data: {
        kind: "terminal",
        title: "用户请求",
        terminalKind: "input",
        layoutWidth: TERMINAL_WIDTH,
        layoutHeight: TERMINAL_HEIGHT,
      } satisfies CanvasNodeData,
    },
    ...flatAgents.map(({ id, path, agent }) => ({
      id,
      type: "agent",
      meta: { position: { x: 0, y: 0 } },
      data: agentNodeData(agent, path, readOnly),
    })),
    {
      id: "terminal-output",
      type: "terminal-output",
      meta: { position: { x: 0, y: 0 } },
      data: {
        kind: "terminal",
        title: "最终回复",
        terminalKind: "output",
        layoutWidth: TERMINAL_WIDTH,
        layoutHeight: TERMINAL_HEIGHT,
      } satisfies CanvasNodeData,
    },
  ];

  return { nodes: layoutWorkflow(nodes, edges, direction), edges };
}

function structureKey(draft: AgentDraft): string {
  const visit = (agent: AgentDraft): unknown => [
    agent.agentType ?? "llm",
    agent.subAgents.map(visit),
  ];
  return JSON.stringify(visit(draft));
}

function edgeKey(edge: WorkflowEdge): string {
  return [
    edge.sourceNodeID,
    edge.sourcePortID ?? "",
    edge.targetNodeID,
    edge.targetPortID ?? "",
  ].join(":");
}

function mergeLiveWorkflow(
  next: WorkflowJSON,
  current: WorkflowJSON | null,
  preserveLayout: boolean,
  preserveEdges: boolean,
): WorkflowJSON {
  if (!current) return next;
  const currentNodes = new Map(current.nodes.map((node) => [node.id, node]));
  const nextIds = new Set(next.nodes.map((node) => node.id));
  const nodes = next.nodes.map((node) => {
    const currentNode = currentNodes.get(node.id);
    return preserveLayout && currentNode?.meta?.position
      ? {
          ...node,
          meta: { ...node.meta, position: currentNode.meta.position },
        }
      : node;
  });
  if (!preserveEdges) return { nodes, edges: next.edges };

  const retainedEdges = current.edges.filter(
    (edge) => nextIds.has(edge.sourceNodeID) && nextIds.has(edge.targetNodeID),
  );
  const retainedKeys = new Set(retainedEdges.map(edgeKey));
  const currentIds = new Set(current.nodes.map((node) => node.id));
  const edgesForNewNodes = next.edges.filter(
    (edge) =>
      (!currentIds.has(edge.sourceNodeID) || !currentIds.has(edge.targetNodeID)) &&
      !retainedKeys.has(edgeKey(edge)),
  );
  return {
    nodes,
    edges: [...retainedEdges, ...edgesForNewNodes],
  };
}

type CanvasActions = {
  onSelect: (path: NodePath) => void;
  onDelete: (path: NodePath) => void;
};

const CanvasActionsContext = createContext<CanvasActions | null>(null);

function CanvasDeleteIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5" />
    </svg>
  );
}

function AgentCardContent({
  data,
  onSelect,
}: {
  data: CanvasNodeData;
  onSelect?: () => void;
}) {
  const type = data.pattern ?? "llm";
  const showModelCapabilities = showsModelCapabilities(type);
  return (
    <div className={`abc-agent-card is-${type}`} onClick={onSelect}>
      <div className="abc-agent-card-head">
        <span
          className="abc-agent-card-mark"
          title={PATTERN_COPY[type].label}
        >
          <CanvasAgentTypeIcon type={type} />
        </span>
        <span className="abc-agent-card-identity">
          <strong
            className={data.nameMissing ? "is-name-missing" : undefined}
            title={data.title}
          >
            {data.title}
          </strong>
          {showModelCapabilities && (
            <span className="abc-agent-card-model" title={data.modelLabel}>
              {data.modelLabel}
            </span>
          )}
        </span>
      </div>
      <div className="abc-agent-card-main">
        <p title={data.description}>{data.description}</p>
      </div>
      {showModelCapabilities && (
        <div className="abc-agent-card-stats" aria-label="Agent 能力统计">
          <span title={`技能 ${data.skillCount ?? 0} 个`}>
            <AgentSkillCountIcon />
            <b>{data.skillCount ?? 0}</b>
          </span>
          <span title={`工具 ${data.toolCount ?? 0} 个`}>
            <AgentToolCountIcon />
            <b>{data.toolCount ?? 0}</b>
          </span>
        </div>
      )}
    </div>
  );
}

function FlowgramCanvasNode(props: WorkflowNodeProps) {
  const { data: rawData, selected, readonly } = useNodeRender(props.node);
  const actions = useContext(CanvasActionsContext);
  const data = rawData as CanvasNodeData;
  if (data.kind === "terminal") {
    const input = data.terminalKind === "input";
    return (
      <WorkflowNodeRenderer
        node={props.node}
        className={`abc-terminal is-${input ? "input" : "output"}`}
        portClassName="abc-flowgram-port"
      >
        <span className="abc-terminal-mark" aria-hidden="true">
          {input ? <TerminalUserRequestIcon /> : <TerminalFinalReplyIcon />}
        </span>
        <span className="abc-terminal-title">{data.title}</span>
      </WorkflowNodeRenderer>
    );
  }

  const type = data.pattern ?? "llm";
  const removable = !readonly && !!data.path && data.path.length > 0;
  return (
    <WorkflowNodeRenderer
      node={props.node}
      className={`abc-node is-${type}${selected ? " is-selected" : ""}`}
      portClassName="abc-flowgram-port"
      portPrimaryColor="#8790b9"
      portSecondaryColor="#c9cdd4"
      portBackgroundColor="#ffffff"
    >
      <AgentCardContent
        data={data}
        onSelect={
          actions && data.path ? () => actions.onSelect(data.path!) : undefined
        }
      />
      {removable && (
        <button
          type="button"
          className="abc-node-delete flow-canvas-not-draggable"
          aria-label={`删除 ${data.title}`}
          title="删除节点"
          onClick={(event) => {
            event.stopPropagation();
            actions?.onDelete(data.path!);
          }}
        >
          <CanvasDeleteIcon />
        </button>
      )}
    </WorkflowNodeRenderer>
  );
}

function createNodeRegistries(
  direction: CanvasDirection,
): WorkflowNodeRegistry[] {
  const inputLocation = direction === "vertical" ? "top" : "left";
  const outputLocation = direction === "vertical" ? "bottom" : "right";
  return [
    {
      type: "agent",
      meta: {
        defaultPorts: [
          { type: "input", location: inputLocation },
          { type: "output", location: outputLocation },
        ],
      },
    },
    {
      type: "terminal-input",
      meta: { defaultPorts: [{ type: "output", location: outputLocation }] },
    },
    {
      type: "terminal-output",
      meta: { defaultPorts: [{ type: "input", location: inputLocation }] },
    },
  ];
}

export interface AgentBuildCanvasProps {
  draft: AgentDraft;
  selectedPath: NodePath;
  onSelect: (path: NodePath) => void;
  onAdd: (path: NodePath) => void;
  onInsert: (parentPath: NodePath, index: number) => void;
  onDelete: (path: NodePath) => void;
  /** Show the graph without any structure-changing actions. */
  readOnly?: boolean;
  /** Allow pan and zoom while remaining read-only. */
  interactivePreview?: boolean;
  /** Lay out the workflow from left to right or top to bottom. */
  direction?: CanvasDirection;
}

type CanvasLifecycleBridgeProps = {
  canvasRef: RefObject<HTMLDivElement | null>;
  direction: CanvasDirection;
  draft: AgentDraft;
  liveWorkflowRef: MutableRefObject<WorkflowJSON | null>;
  syncingRef: MutableRefObject<boolean>;
  lastStructureRef: MutableRefObject<string>;
  lastDirectionRef: MutableRefObject<CanvasDirection>;
  selectedPath: NodePath;
  scheduleFit: (context: FreeLayoutPluginContext, attempt?: number) => void;
  workflow: WorkflowJSON;
};

function CanvasLifecycleBridge({
  canvasRef,
  direction,
  draft,
  liveWorkflowRef,
  syncingRef,
  lastStructureRef,
  lastDirectionRef,
  selectedPath,
  scheduleFit,
  workflow,
}: CanvasLifecycleBridgeProps) {
  const editorContext = useClientContext();

  useEffect(() => {
    const nextStructure = structureKey(draft);
    const structureChanged = lastStructureRef.current !== nextStructure;
    const directionChanged = lastDirectionRef.current !== direction;
    const preserveLayout = !directionChanged && !!liveWorkflowRef.current;
    const merged = mergeLiveWorkflow(
      workflow,
      liveWorkflowRef.current,
      preserveLayout,
      !structureChanged && !directionChanged,
    );
    syncingRef.current = true;
    editorContext.operation.fromJSON(merged);
    liveWorkflowRef.current = merged;
    syncingRef.current = false;
    lastStructureRef.current = nextStructure;
    lastDirectionRef.current = direction;
    if (structureChanged || directionChanged) scheduleFit(editorContext);
  }, [
    direction,
    draft,
    editorContext,
    lastDirectionRef,
    lastStructureRef,
    liveWorkflowRef,
    scheduleFit,
    syncingRef,
    workflow,
  ]);

  useEffect(() => {
    const node = editorContext.document.getNode(pathId(selectedPath));
    if (node) editorContext.selection.selection = [node];
  }, [editorContext, selectedPath]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() => scheduleFit(editorContext));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [canvasRef, editorContext, scheduleFit]);

  return null;
}

export function AgentBuildCanvas({
  draft,
  selectedPath,
  onSelect,
  onAdd,
  onInsert,
  onDelete,
  readOnly = false,
  interactivePreview = false,
  direction = "vertical",
}: AgentBuildCanvasProps) {
  void onInsert;
  void interactivePreview;
  const canvasRef = useRef<HTMLDivElement>(null);
  const liveWorkflowRef = useRef<WorkflowJSON | null>(null);
  const syncingRef = useRef(false);
  const fitFrameRef = useRef<number | null>(null);
  const lastStructureRef = useRef(structureKey(draft));
  const lastDirectionRef = useRef(direction);

  const workflow = useMemo(
    () => buildFlowgramWorkflow(draft, direction, readOnly),
    [direction, draft, readOnly],
  );
  const nodeRegistries = useMemo(
    () => createNodeRegistries(direction),
    [direction],
  );

  const scheduleFit = useCallback(
    (context: FreeLayoutPluginContext, attempt = 0) => {
      if (fitFrameRef.current !== null) {
        window.cancelAnimationFrame(fitFrameRef.current);
      }
      fitFrameRef.current = window.requestAnimationFrame(() => {
        fitFrameRef.current = window.requestAnimationFrame(() => {
          fitFrameRef.current = null;
          const container = canvasRef.current;
          if (
            container &&
            (container.clientWidth === 0 || container.clientHeight === 0) &&
            attempt < 8
          ) {
            scheduleFit(context, attempt + 1);
            return;
          }
          void context.tools.fitView(false);
        });
      });
    },
    [],
  );

  const editorProps = useMemo<FreeLayoutProps>(
    () => ({
      background: false,
      readonly: readOnly,
      enableReadonlyNodeDragging: false,
      initialData: workflow,
      nodeRegistries,
      materials: { renderDefaultNode: FlowgramCanvasNode },
      twoWayConnection: false,
      canAddLine: (_ctx, fromPort, toPort) =>
        !readOnly &&
        fromPort.node.id !== toPort.node.id &&
        fromPort.node.id !== "terminal-output" &&
        toPort.node.id !== "terminal-input",
      canDeleteLine: () => !readOnly,
      canDeleteNode: () => false,
      setLineRenderType: () => LineType.LINE_CHART,
      lineColor: {
        hidden: "transparent",
        default: "#C9CDD4",
        drawing: "#8790B9",
        hovered: "#8790B9",
        selected: "#8790B9",
        error: "#D54941",
        flowing: "#8790B9",
      },
      history: {
        enable: true,
        enableChangeNode: true,
      },
      onContentChange(ctx) {
        if (!syncingRef.current) {
          liveWorkflowRef.current = ctx.document.toJSON();
        }
      },
      onInit(ctx) {
        liveWorkflowRef.current = ctx.document.toJSON();
      },
      onAllLayersRendered(ctx) {
        scheduleFit(ctx);
      },
    }),
    [nodeRegistries, readOnly, scheduleFit, workflow],
  );

  useEffect(
    () => () => {
      if (fitFrameRef.current !== null) {
        window.cancelAnimationFrame(fitFrameRef.current);
      }
    },
    [],
  );

  const canvasActions = useMemo(
    () => (readOnly ? null : { onSelect, onDelete }),
    [onDelete, onSelect, readOnly],
  );

  return (
    <CanvasActionsContext.Provider value={canvasActions}>
      <section
        className={`abc-root is-${direction}${readOnly ? " is-readonly" : ""}`}
        aria-label={readOnly ? "只读 Agent 执行画布" : "Agent 执行画布"}
      >
        <div ref={canvasRef} className="abc-canvas">
          <FreeLayoutEditorProvider
            key={`${direction}-${readOnly ? "readonly" : "editable"}`}
            {...editorProps}
          >
            <EditorRenderer className="abc-flowgram-editor" />
            <CanvasLifecycleBridge
              canvasRef={canvasRef}
              direction={direction}
              draft={draft}
              liveWorkflowRef={liveWorkflowRef}
              syncingRef={syncingRef}
              lastStructureRef={lastStructureRef}
              lastDirectionRef={lastDirectionRef}
              selectedPath={selectedPath}
              scheduleFit={scheduleFit}
              workflow={workflow}
            />
            {!readOnly && (
              <Button
                type="button"
                color="secondary"
                variant="outline"
                size="sm"
                pill={false}
                className="abc-add-node"
                onClick={() => onAdd([])}
              >
                <CreateAddIcon />
                添加节点
              </Button>
            )}
          </FreeLayoutEditorProvider>
        </div>
      </section>
    </CanvasActionsContext.Provider>
  );
}
