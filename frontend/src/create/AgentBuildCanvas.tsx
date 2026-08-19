import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  getSmoothStepPath,
  getStraightPath,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesInitialized,
  useNodesState,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type MiniMapNodeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Plus, Trash2 } from "lucide-react";
import type { AgentDraft } from "./types";
import {
  AgentSkillCountIcon,
  AgentToolCountIcon,
  CanvasAgentTypeIcon,
} from "../ui/CapabilityIcons";
import {
  TerminalFinalReplyIcon,
  TerminalUserRequestIcon,
} from "../ui/icons/CreateAgentIcons";
import "@xyflow/react/dist/style.css";
import "./AgentBuildCanvas.css";

type NodePath = number[];
type AgentType = NonNullable<AgentDraft["agentType"]>;

const PATTERN_COPY: Record<
  AgentType,
  { label: string; description: string }
> = {
  llm: {
    label: "智能体",
    description: "理解任务并直接完成一个具体工作",
  },
  sequential: {
    label: "分步协作",
    description: "内部步骤按照顺序依次执行",
  },
  parallel: {
    label: "同时处理",
    description: "内部步骤同时工作，完成后统一汇总",
  },
  loop: {
    label: "循环执行",
    description: "重复执行内部步骤，直到满足停止条件",
  },
  a2a: {
    label: "远程智能体",
    description: "调用已经存在的远程 Agent",
  },
};

type CanvasNodeData = {
  kind: "agent" | "terminal" | "junction";
  path?: NodePath;
  agent?: AgentDraft;
  title: string;
  nameMissing?: boolean;
  pattern?: AgentType;
  modelLabel?: string;
  description?: string;
  toolCount?: number;
  skillCount?: number;
  childCount?: number;
  containedIn?: AgentType;
  layoutWidth?: number;
  layoutHeight?: number;
  terminalKind?: "input" | "output";
  junctionKind?: "split" | "merge";
  junctionDirection?: CanvasDirection;
};

type CanvasNode = Node<CanvasNodeData>;

const NODE_WIDTH = 214;
const NODE_HEIGHT = 168;
const COMPACT_NODE_HEIGHT = 138;
const READ_ONLY_NODE_HEIGHT = 133;
const READ_ONLY_COMPACT_NODE_HEIGHT = 104;

function canvasAgentTitle(agent: AgentDraft): string {
  if (agent.agentType === "a2a") return "远程智能体";
  return agent.name.trim() || "名称未配置";
}
function canvasAgentModel(agent: AgentDraft): string {
  return agent.modelName?.trim() || agent.model?.trim() || "模型未配置";
}

function uniqueCapabilityCount(values: Array<string | undefined>): number {
  return new Set(
    values.map((value) => value?.trim()).filter((value): value is string => !!value),
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
const TERMINAL_WIDTH = 120;
const TERMINAL_HEIGHT = 52;
const FIGMA_FLOW_LINE_LENGTH = 69;
const FLOW_HANDLE_SIZE = 7;
const GROUP_HEADER_HEIGHT = 46;
const GROUP_SUMMARY_HEIGHT = 122;
const GROUP_COMPACT_SUMMARY_HEIGHT = 84;
const READ_ONLY_GROUP_SUMMARY_HEIGHT = 84;
const READ_ONLY_GROUP_COMPACT_SUMMARY_HEIGHT = 46;
const GROUP_MIN_WIDTH = 310;
const GROUP_PADDING = 24;
const GROUP_BOUNDARY_PADDING = 56;
const GROUP_GAP = 40;
const LOOP_EDGE_SPACE = 58;
const PARALLEL_RAIL_SPACE = 44;
const JUNCTION_SIZE = 18;
const MINIMAP_ENABLED = false;

const isContainerType = (type: AgentType) =>
  type === "sequential" || type === "parallel" || type === "loop";

const showsModelCapabilities = (type: AgentType): boolean => type === "llm";

const nodeHeight = (type: AgentType, readOnly: boolean): number =>
  showsModelCapabilities(type)
    ? readOnly
      ? READ_ONLY_NODE_HEIGHT
      : NODE_HEIGHT
    : readOnly
      ? READ_ONLY_COMPACT_NODE_HEIGHT
      : COMPACT_NODE_HEIGHT;

const groupSummaryHeight = (type: AgentType, readOnly: boolean): number =>
  showsModelCapabilities(type)
    ? readOnly
      ? READ_ONLY_GROUP_SUMMARY_HEIGHT
      : GROUP_SUMMARY_HEIGHT
    : readOnly
      ? READ_ONLY_GROUP_COMPACT_SUMMARY_HEIGHT
      : GROUP_COMPACT_SUMMARY_HEIGHT;

const groupContentTop = (type: AgentType, readOnly: boolean): number =>
  GROUP_HEADER_HEIGHT + groupSummaryHeight(type, readOnly);

function rendersAsGroup(agent: AgentDraft, path: NodePath): boolean {
  const type = agent.agentType ?? "llm";
  return (
    isContainerType(type) ||
    (type === "llm" && (path.length === 0 || agent.subAgents.length > 0))
  );
}

export type CanvasDirection = "horizontal" | "vertical";

function measureAgent(
  agent: AgentDraft,
  path: NodePath = [],
  direction: CanvasDirection = "horizontal",
  readOnly = false,
): { width: number; height: number } {
  const type = agent.agentType ?? "llm";
  if (!rendersAsGroup(agent, path)) {
    return { width: NODE_WIDTH, height: nodeHeight(type, readOnly) };
  }
  const contentTop = groupContentTop(type, readOnly);
  const sizes = agent.subAgents.map((child, index) =>
    measureAgent(child, [...path, index], direction, readOnly),
  );
  const widestChild = sizes.length
    ? Math.max(...sizes.map((size) => size.width))
    : 0;
  const tallestChild = sizes.length
    ? Math.max(...sizes.map((size) => size.height))
    : 0;
  const flowPadding = sizes.length && type !== "parallel"
    ? GROUP_BOUNDARY_PADDING
    : GROUP_PADDING;
  const horizontalChildren = direction === "horizontal"
    ? type !== "parallel"
    : type === "parallel";
  if (sizes.length === 0) {
    return { width: GROUP_MIN_WIDTH, height: contentTop };
  }
  const bottomSpace = type === "loop" ? LOOP_EDGE_SPACE : 0;
  const parallelHorizontalRails = type === "parallel" && !horizontalChildren
    ? PARALLEL_RAIL_SPACE * 2
    : 0;
  const parallelVerticalRails = type === "parallel" && horizontalChildren
    ? PARALLEL_RAIL_SPACE * 2
    : 0;
  if (!horizontalChildren) {
    return {
      width: Math.max(
        GROUP_MIN_WIDTH,
        widestChild + GROUP_PADDING * 2 + parallelHorizontalRails,
      ),
      height:
        contentTop +
        flowPadding +
        sizes.reduce((sum, size) => sum + size.height, 0) +
        GROUP_GAP * Math.max(0, sizes.length - 1) +
        bottomSpace +
        flowPadding,
    };
  }
  return {
    width: Math.max(
      GROUP_MIN_WIDTH,
      sizes.reduce((sum, size) => sum + size.width, 0) +
      GROUP_GAP * Math.max(0, sizes.length - 1) +
      flowPadding * 2,
    ),
    height:
      contentTop +
      GROUP_PADDING +
      parallelVerticalRails +
      tallestChild +
      bottomSpace +
      GROUP_PADDING,
  };
}

function pathId(path: NodePath): string {
  return path.length === 0 ? "agent-root" : `agent-${path.join("-")}`;
}

function samePath(a: NodePath, b: NodePath): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function structureKey(root: AgentDraft): string {
  const visit = (node: AgentDraft): unknown => [
    node.agentType ?? "llm",
    node.subAgents.map(visit),
  ];
  return JSON.stringify(visit(root));
}

type CanvasEdgeData = {
  insert?: { parentPath: NodePath; index: number };
  loop?: boolean;
  tone?: AgentType;
  figmaFlow?: boolean;
  semantic?: "call" | "sequence" | "branch" | "merge" | "return";
};

type CanvasEdge = Edge<CanvasEdgeData>;

function makeEdge(
  source: string,
  target: string,
  label?: string,
  options?: {
    loop?: boolean;
    tone?: AgentType;
    insert?: CanvasEdgeData["insert"];
    figmaFlow?: boolean;
    semantic?: CanvasEdgeData["semantic"];
    sourceHandle?: string;
    targetHandle?: string;
  },
): CanvasEdge {
  const edgeColor = options?.figmaFlow
    ? "#C9CDD4"
    : options?.tone === "sequential"
      ? "hsl(213 40% 40%)"
      : options?.tone === "parallel"
        ? "hsl(40 43% 38%)"
        : options?.tone === "loop"
          ? "hsl(151 34% 34%)"
          : "hsl(220 9% 38%)";
  return {
    id: `${source}-${target}${options?.loop ? "-loop" : ""}`,
    source,
    target,
    sourceHandle: options?.loop ? "loop-source" : options?.sourceHandle,
    targetHandle: options?.loop ? "loop-target" : options?.targetHandle,
    label,
    type: "insertStep",
    data: options
      ? {
          insert: options.insert,
          loop: options.loop,
          tone: options.tone,
          figmaFlow: options.figmaFlow,
          semantic: options.semantic,
        }
      : undefined,
    animated: options?.loop,
    markerEnd: options?.figmaFlow
      ? undefined
      : {
          type: MarkerType.ArrowClosed,
          width: 16,
          height: 16,
          color: edgeColor,
        },
    style: {
      stroke: edgeColor,
      strokeWidth: 1.5,
    },
    zIndex: options?.figmaFlow ? 0 : 2,
    labelStyle: {
      fill: "hsl(215 14% 42%)",
      fontSize: 10,
      fontWeight: 600,
    },
    labelBgStyle: {
      fill: "hsl(var(--background))",
      fillOpacity: 0.92,
    },
  };
}

function buildCanvasGraph(
  root: AgentDraft,
  direction: CanvasDirection,
  readOnly = false,
): {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
} {
  const nodes: CanvasNode[] = [
    {
      id: "terminal-input",
      type: "terminal",
      position: { x: 0, y: 0 },
      data: { kind: "terminal", title: "用户请求", terminalKind: "input" },
      selectable: false,
      draggable: false,
    },
    {
      id: "terminal-output",
      type: "terminal",
      position: { x: 0, y: 0 },
      data: { kind: "terminal", title: "最终回复", terminalKind: "output" },
      selectable: false,
      draggable: false,
    },
  ];
  const edges: CanvasEdge[] = [];
  const groupExitIds = new Map<string, string[]>();

  function addContainedNode(
    agent: AgentDraft,
    path: NodePath,
    parentId: string,
    position: { x: number; y: number },
    containedIn: AgentType,
  ): string {
    const type = agent.agentType ?? "llm";
    const id = pathId(path);
    if (rendersAsGroup(agent, path)) {
      addGroupNode(agent, path, parentId, position, containedIn);
      return id;
    }
    const height = nodeHeight(type, readOnly);
    nodes.push({
      id,
      type: "agent",
      parentId,
      extent: "parent",
      position,
      style: { width: NODE_WIDTH, height },
      data: {
        kind: "agent",
        path,
        agent,
        title: canvasAgentTitle(agent),
        ...canvasAgentCardData(agent),
        nameMissing: type !== "a2a" && agent.name.trim().length === 0,
        pattern: type,
        childCount: agent.subAgents.length,
        containedIn,
        layoutWidth: NODE_WIDTH,
        layoutHeight: height,
      },
    });
    return id;
  }

  function addParallelJunction(
    kind: "split" | "merge",
    parentId: string,
    path: NodePath,
    position: { x: number; y: number },
    junctionDirection: CanvasDirection,
  ): string {
    const id = `${pathId(path)}-parallel-${kind}`;
    nodes.push({
      id,
      type: "junction",
      parentId,
      extent: "parent",
      position,
      style: { width: JUNCTION_SIZE, height: JUNCTION_SIZE },
      selectable: false,
      draggable: false,
      connectable: false,
      data: {
        kind: "junction",
        title: kind === "split" ? "并行分发" : "并行汇合",
        junctionKind: kind,
        junctionDirection,
      },
    });
    return id;
  }

  function addGroupNode(
    agent: AgentDraft,
    path: NodePath,
    parentId?: string,
    position = { x: 0, y: 0 },
    containedIn?: AgentType,
  ): string {
    const type = agent.agentType ?? "sequential";
    const contentTop = groupContentTop(type, readOnly);
    const id = pathId(path);
    const size = measureAgent(agent, path, direction, readOnly);
    nodes.push({
      id,
      type: "group",
      parentId,
      extent: parentId ? "parent" : undefined,
      position,
      style: { width: size.width, height: size.height },
      data: {
        kind: "agent",
        path,
        agent,
        title: canvasAgentTitle(agent),
        ...canvasAgentCardData(agent),
        nameMissing: type !== "a2a" && agent.name.trim().length === 0,
        pattern: type,
        childCount: agent.subAgents.length,
        containedIn,
        layoutWidth: size.width,
        layoutHeight: size.height,
      },
    });

    const childSizes = agent.subAgents.map((child, index) =>
      measureAgent(child, [...path, index], direction, readOnly),
    );
    const flowPadding = childSizes.length && type !== "parallel"
      ? GROUP_BOUNDARY_PADDING
      : GROUP_PADDING;
    const horizontalChildren = direction === "horizontal"
      ? type !== "parallel"
      : type === "parallel";
    let cursor = horizontalChildren ? flowPadding : GROUP_BOUNDARY_PADDING;
    const childIds = agent.subAgents.map((child, index) => {
      const childSize = childSizes[index];
      const childPosition =
        horizontalChildren
          ? {
              x: cursor,
              y:
                contentTop +
                GROUP_PADDING +
                (type === "parallel" ? PARALLEL_RAIL_SPACE : 0),
            }
          : {
              x:
                type === "parallel"
                  ? GROUP_PADDING + PARALLEL_RAIL_SPACE
                  : (size.width - childSize.width) / 2,
              y: contentTop + cursor,
            };
      cursor +=
        (horizontalChildren ? childSize.width : childSize.height) + GROUP_GAP;
      return addContainedNode(
        child,
        [...path, index],
        id,
        childPosition,
        type,
      );
    });

    if (childIds.length === 0) {
      groupExitIds.set(id, [id]);
      return id;
    }

    if (type === "llm") {
      for (let index = 0; index < childIds.length - 1; index += 1) {
        edges.push(
          makeEdge(childIds[index], childIds[index + 1], "然后", {
            tone: "llm",
            semantic: "sequence",
            insert: { parentPath: path, index: index + 1 },
          }),
        );
      }
      groupExitIds.set(id, [id]);
    }

    if (type === "sequential" || type === "loop") {
      for (let index = 0; index < childIds.length - 1; index += 1) {
        edges.push(
          makeEdge(childIds[index], childIds[index + 1], "然后", {
            tone: type,
            semantic: "sequence",
            insert: { parentPath: path, index: index + 1 },
          }),
        );
      }
      if (type === "loop" && childIds.length > 1) {
        edges.push(
          makeEdge(childIds[childIds.length - 1], childIds[0], "继续循环", {
            loop: true,
            tone: "loop",
            semantic: "return",
          }),
        );
      }
      groupExitIds.set(id, [id]);
    }

    if (type === "parallel") {
      const junctionDirection = horizontalChildren ? "vertical" : "horizontal";
      const tallestChild = Math.max(...childSizes.map((child) => child.height));
      const widestChild = Math.max(...childSizes.map((child) => child.width));
      const stackedHeight = childSizes.reduce(
        (total, child) => total + child.height,
        GROUP_GAP * Math.max(0, childSizes.length - 1),
      );
      const splitPosition = horizontalChildren
        ? {
            x: size.width / 2 - JUNCTION_SIZE / 2,
            y:
              contentTop +
              GROUP_PADDING +
              PARALLEL_RAIL_SPACE / 2 -
              JUNCTION_SIZE / 2,
          }
        : {
            x:
              GROUP_PADDING +
              PARALLEL_RAIL_SPACE / 2 -
              JUNCTION_SIZE / 2,
            y:
              contentTop +
              GROUP_PADDING +
              (stackedHeight - JUNCTION_SIZE) / 2,
          };
      const mergePosition = horizontalChildren
        ? {
            x: size.width / 2 - JUNCTION_SIZE / 2,
            y:
              contentTop +
              GROUP_PADDING +
              PARALLEL_RAIL_SPACE +
              tallestChild +
              PARALLEL_RAIL_SPACE / 2 -
              JUNCTION_SIZE / 2,
          }
        : {
            x:
              GROUP_PADDING +
              PARALLEL_RAIL_SPACE +
              widestChild +
              PARALLEL_RAIL_SPACE / 2 -
              JUNCTION_SIZE / 2,
            y:
              contentTop +
              GROUP_PADDING +
              (stackedHeight - JUNCTION_SIZE) / 2,
          };
      const splitId = addParallelJunction(
        "split",
        id,
        path,
        splitPosition,
        junctionDirection,
      );
      const mergeId = addParallelJunction(
        "merge",
        id,
        path,
        mergePosition,
        junctionDirection,
      );
      childIds.forEach((childId) => {
        edges.push(
          makeEdge(splitId, childId, undefined, {
            tone: "parallel",
            semantic: "branch",
          }),
          makeEdge(childId, mergeId, undefined, {
            tone: "parallel",
            semantic: "merge",
          }),
        );
      });
      groupExitIds.set(id, [id]);
    }
    return id;
  }

  const addTopLevelNode = (agent: AgentDraft, path: NodePath): string[] => {
    const type = agent.agentType ?? "llm";
    const id = pathId(path);
    if (rendersAsGroup(agent, path)) {
      addGroupNode(agent, path);
      return groupExitIds.get(id) ?? [id];
    }
    const height = nodeHeight(type, readOnly);
    nodes.push({
      id,
      type: "agent",
      position: { x: 0, y: 0 },
      style: { width: NODE_WIDTH, height },
      data: {
        kind: "agent",
        path,
        agent,
        title: canvasAgentTitle(agent),
        ...canvasAgentCardData(agent),
        nameMissing: type !== "a2a" && agent.name.trim().length === 0,
        pattern: type,
        childCount: agent.subAgents.length,
        layoutWidth: NODE_WIDTH,
        layoutHeight: height,
      },
    });
    return [id];
  };

  const rootId = pathId([]);
  const exits = addTopLevelNode(root, []);
  edges.push(makeEdge("terminal-input", rootId, undefined, { figmaFlow: true }));
  exits.forEach((exitId) =>
    edges.push(makeEdge(exitId, "terminal-output", undefined, { figmaFlow: true })),
  );
  return layoutGraph(nodes, edges, direction);
}

function layoutGraph(
  nodes: CanvasNode[],
  edges: CanvasEdge[],
  direction: CanvasDirection,
) {
  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: direction === "vertical" ? "TB" : "LR",
    // Invisible React Flow handles inset each endpoint by half their diameter.
    ranksep: FIGMA_FLOW_LINE_LENGTH + FLOW_HANDLE_SIZE,
    nodesep: 34,
    edgesep: 14,
    marginx: 24,
    marginy: 24,
  });
  const nodeById = new Map(nodes.map((node) => [node.id, node] as const));
  const topLevelId = (nodeId: string): string => {
    let node = nodeById.get(nodeId);
    while (node?.parentId) {
      node = nodeById.get(node.parentId);
    }
    return node?.id ?? nodeId;
  };
  nodes.filter((node) => !node.parentId).forEach((node) => {
    const terminal = node.data.kind === "terminal";
    const groupHeaderAligned = node.type === "group" && direction === "horizontal";
    graph.setNode(node.id, {
      width: terminal
        ? TERMINAL_WIDTH
        : node.data.layoutWidth ?? NODE_WIDTH,
      height: terminal
        ? TERMINAL_HEIGHT
        : groupHeaderAligned
          ? GROUP_HEADER_HEIGHT
          : node.data.layoutHeight ?? NODE_HEIGHT,
    });
  });
  edges.forEach((edge) => {
    const source = topLevelId(edge.source);
    const target = topLevelId(edge.target);
    if (source !== target) graph.setEdge(source, target);
  });
  dagre.layout(graph);
  return {
    nodes: nodes.map((node) => {
      if (node.parentId) return node;
      const position = graph.node(node.id) as { x: number; y: number };
      const terminal = node.data.kind === "terminal";
      const groupHeaderAligned = node.type === "group" && direction === "horizontal";
      const width = terminal
        ? TERMINAL_WIDTH
        : node.data.layoutWidth ?? NODE_WIDTH;
      const height = terminal
        ? TERMINAL_HEIGHT
        : groupHeaderAligned
          ? GROUP_HEADER_HEIGHT
          : node.data.layoutHeight ?? NODE_HEIGHT;
      return {
        ...node,
        position: { x: position.x - width / 2, y: position.y - height / 2 },
      };
    }),
    edges,
  };
}

type CanvasActions = {
  onAdd: (path: NodePath) => void;
  onInsert: (parentPath: NodePath, index: number) => void;
  onDelete: (path: NodePath) => void;
};

const CanvasActionsContext = createContext<CanvasActions | null>(null);
const CanvasDirectionContext = createContext<CanvasDirection>("horizontal");

function InsertStepEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  label,
  data,
}: EdgeProps<CanvasEdge>) {
  const actions = useContext(CanvasActionsContext);
  const [showInsert, setShowInsert] = useState(false);
  const [edgePath, labelX, labelY] = data?.figmaFlow
    ? getStraightPath({ sourceX, sourceY, targetX, targetY })
    : getSmoothStepPath({
        sourceX,
        sourceY,
        targetX,
        targetY,
        sourcePosition,
        targetPosition,
        offset: data?.loop ? 28 : 20,
      });
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={style}
      />
      {actions && data?.insert && (
        <path
          d={edgePath}
          className="abc-edge-hover-path"
          onPointerEnter={() => setShowInsert(true)}
          onPointerLeave={() => setShowInsert(false)}
        />
      )}
      {(label || (actions && data?.insert)) && (
        <EdgeLabelRenderer>
          <div
            className={`abc-edge-tools${
              actions && data?.insert ? " can-insert" : ""
            }${showInsert ? " is-visible" : ""}`}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
            onPointerEnter={() => setShowInsert(true)}
            onPointerLeave={() => setShowInsert(false)}
          >
            {label && <span className="abc-edge-label">{label}</span>}
            {actions && data?.insert && (
              <button
                type="button"
                className="abc-edge-add nodrag nopan"
                aria-label="在这里插入步骤"
                title="在这里插入步骤"
                onClick={(event) => {
                  event.stopPropagation();
                  actions?.onInsert(
                    data.insert!.parentPath,
                    data.insert!.index,
                  );
                }}
              >
                <Plus />
              </button>
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

function AgentCardContent({
  data,
  onAdd,
}: {
  data: CanvasNodeData;
  onAdd?: () => void;
}) {
  const patternLabel = PATTERN_COPY[data.pattern ?? "llm"].label;
  const type = data.pattern ?? "llm";
  const showModelCapabilities = showsModelCapabilities(type);
  return (
    <div className={`abc-agent-card is-${type}`}>
      <div className="abc-agent-card-head">
        <span className="abc-agent-card-mark" title={patternLabel}>
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
        {onAdd && (
          <Button
            type="button"
            color="secondary"
            variant="outline"
            size="sm"
            pill={false}
            className="abc-agent-card-add nodrag nopan"
            onClick={(event) => {
              event.stopPropagation();
              onAdd();
            }}
          >
            <Plus />
            添加子 Agent
          </Button>
        )}
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

function AgentCanvasNode({ data, selected }: NodeProps<CanvasNode>) {
  const actions = useContext(CanvasActionsContext);
  const direction = useContext(CanvasDirectionContext);
  const targetPosition = direction === "vertical" ? Position.Top : Position.Left;
  const sourcePosition = direction === "vertical" ? Position.Bottom : Position.Right;
  const loopPosition = direction === "vertical" ? Position.Right : Position.Bottom;
  const type = data.pattern ?? "llm";
  return (
    <div
      className={`abc-node is-${type}${
        data.containedIn ? ` is-contained-in-${data.containedIn}` : ""
      }${selected ? " is-selected" : ""}`}
    >
      <Handle type="target" position={targetPosition} className="abc-handle" />
      <AgentCardContent
        data={data}
        onAdd={
          actions && data.path !== undefined && type !== "a2a"
            ? () => actions.onAdd(data.path!)
            : undefined
        }
      />
      {actions && data.path !== undefined && data.path.length > 0 && (
        <button
          type="button"
          className="abc-node-delete nodrag nopan"
          aria-label={`删除 ${data.title}`}
          title="删除节点"
          onClick={(event) => {
            event.stopPropagation();
            actions?.onDelete(data.path!);
          }}
        >
          <Trash2 />
        </button>
      )}
      <Handle type="source" position={sourcePosition} className="abc-handle" />
      {data.containedIn === "loop" && (
        <>
          <Handle
            id="loop-target"
            type="target"
            position={loopPosition}
            className="abc-handle abc-loop-handle"
          />
          <Handle
            id="loop-source"
            type="source"
            position={loopPosition}
            className="abc-handle abc-loop-handle"
          />
        </>
      )}
    </div>
  );
}

function AgentGroupNode({ data, selected }: NodeProps<CanvasNode>) {
  const actions = useContext(CanvasActionsContext);
  const direction = useContext(CanvasDirectionContext);
  const targetPosition = direction === "vertical" ? Position.Top : Position.Left;
  const sourcePosition = direction === "vertical" ? Position.Bottom : Position.Right;
  const loopPosition = direction === "vertical" ? Position.Right : Position.Bottom;
  const type = data.pattern ?? "sequential";
  const childCount = data.childCount ?? 0;
  const showModelCapabilities = showsModelCapabilities(type);
  return (
    <div
      className={`abc-group is-${type}${
        childCount > 0 ? " has-children" : " is-empty"
      }${
        data.containedIn ? ` is-contained-in-${data.containedIn}` : ""
      }${selected ? " is-selected" : ""}`}
    >
      <Handle type="target" position={targetPosition} className="abc-handle" />
      <div
        className="abc-group-body"
        aria-label={`${data.title} 的子 Agent 容器`}
      />
      <header className="abc-group-head">
        <span className="abc-group-head-mark" aria-hidden="true">
          <CanvasAgentTypeIcon type={type} />
        </span>
        <span className="abc-group-head-identity">
          <strong
            className={data.nameMissing ? "is-name-missing" : undefined}
            title={data.title}
          >
            {data.title}
          </strong>
          {showModelCapabilities && (
            <small title={data.modelLabel}>{data.modelLabel}</small>
          )}
        </span>
      </header>
      <div className="abc-group-summary">
        <p className="abc-group-description" title={data.description}>
          {data.description}
        </p>
        {actions && data.path !== undefined && (
          <Button
            type="button"
            color="secondary"
            variant="outline"
            size="sm"
            pill={false}
            className="abc-group-summary-add nodrag nopan"
            onClick={(event) => {
              event.stopPropagation();
              actions.onAdd(data.path!);
            }}
          >
            <Plus />
            添加子 Agent
          </Button>
        )}
        {showModelCapabilities && (
          <div className="abc-group-summary-stats" aria-label="Agent 能力统计">
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
      {actions && data.path !== undefined && data.path.length > 0 && (
        <button
          type="button"
          className="abc-node-delete nodrag nopan"
          aria-label={`删除 ${data.title}`}
          title="删除节点"
          onClick={(event) => {
            event.stopPropagation();
            actions?.onDelete(data.path!);
          }}
        >
          <Trash2 />
        </button>
      )}
      <Handle type="source" position={sourcePosition} className="abc-handle" />
      {data.containedIn === "loop" && (
        <>
          <Handle
            id="loop-target"
            type="target"
            position={loopPosition}
            className="abc-handle abc-loop-handle"
          />
          <Handle
            id="loop-source"
            type="source"
            position={loopPosition}
            className="abc-handle abc-loop-handle"
          />
        </>
      )}
    </div>
  );
}

function ParallelJunctionNode({ data }: NodeProps<CanvasNode>) {
  const direction = data.junctionDirection ?? "vertical";
  const split = data.junctionKind === "split";
  const targetPosition = direction === "vertical" ? Position.Top : Position.Left;
  const sourcePosition = direction === "vertical" ? Position.Bottom : Position.Right;
  return (
    <div
      className={`abc-junction is-${split ? "split" : "merge"} is-${direction}`}
      aria-label={data.title}
    >
      <Handle type="target" position={targetPosition} className="abc-handle" />
      <span className="abc-junction-mark" aria-hidden="true" />
      <span className="abc-junction-label">{split ? "分发" : "汇合"}</span>
      <Handle type="source" position={sourcePosition} className="abc-handle" />
    </div>
  );
}

function TerminalNode({ data }: NodeProps<CanvasNode>) {
  const direction = useContext(CanvasDirectionContext);
  const input = data.terminalKind === "input";
  return (
    <div className={`abc-terminal is-${input ? "input" : "output"}`}>
      <Handle
        type="target"
        position={direction === "vertical" ? Position.Top : Position.Left}
        className="abc-handle"
      />
      <span className="abc-terminal-mark" aria-hidden="true">
        {input ? <TerminalUserRequestIcon /> : <TerminalFinalReplyIcon />}
      </span>
      <span className="abc-terminal-title">{data.title}</span>
      <Handle
        type="source"
        position={direction === "vertical" ? Position.Bottom : Position.Right}
        className="abc-handle"
      />
    </div>
  );
}

const NODE_TYPES = {
  agent: AgentCanvasNode,
  group: AgentGroupNode,
  junction: ParallelJunctionNode,
  terminal: TerminalNode,
};

const EDGE_TYPES = {
  insertStep: InsertStepEdge,
};

function CanvasMiniMapNode({
  id,
  x,
  y,
  width,
  height,
  className,
  selected,
  onClick,
}: MiniMapNodeProps) {
  const isGroup = className.includes("abc-minimap-node-group");
  const isTerminal = className.includes("abc-minimap-node-terminal");
  const isLlm = className.includes("is-llm");
  const isExternal = className.includes("is-a2a");
  const radius = Math.min(18, height / 4);
  const nodeClassName = `${className}${selected ? " is-selected" : ""}`;

  if (isTerminal) {
    return (
      <g
        className={nodeClassName}
        onClick={onClick ? (event) => onClick(event, id) : undefined}
      >
        <rect
          className="abc-minimap-shell"
          x={x}
          y={y}
          width={width}
          height={height}
          rx={height / 2}
        />
        <circle
          className="abc-minimap-terminal-dot"
          cx={x + height * 0.34}
          cy={y + height / 2}
          r={Math.max(2.5, height * 0.09)}
        />
      </g>
    );
  }

  if (isGroup) {
    const headerHeight = Math.min(42, Math.max(18, height * 0.22));
    return (
      <g
        className={nodeClassName}
        onClick={onClick ? (event) => onClick(event, id) : undefined}
      >
        <rect
          className="abc-minimap-shell"
          x={x}
          y={y}
          width={width}
          height={height}
          rx={radius}
        />
        <line
          className="abc-minimap-group-divider"
          x1={x}
          x2={x + width}
          y1={y + headerHeight}
          y2={y + headerHeight}
        />
        <rect
          className="abc-minimap-group-title"
          x={x + width * 0.39}
          y={y + headerHeight * 0.38}
          width={width * 0.22}
          height={Math.max(4, headerHeight * 0.2)}
          rx={3}
        />
      </g>
    );
  }

  const iconSize = isLlm ? 0 : Math.min(36, height * 0.5, width * 0.18);
  const sidePadding = Math.max(10, width * 0.08);
  const iconX = x + sidePadding;
  const iconY = y + (height - iconSize) / 2;
  const textX = isLlm
    ? x + sidePadding
    : iconX + iconSize + Math.max(8, width * 0.05);
  const textWidth = Math.max(10, x + width - textX - sidePadding);
  const lineHeight = Math.max(4, height * 0.08);

  return (
    <g
      className={nodeClassName}
      onClick={onClick ? (event) => onClick(event, id) : undefined}
    >
      <rect
        className="abc-minimap-shell"
        x={x}
        y={y}
        width={width}
        height={height}
        rx={radius}
      />
      {!isLlm && <rect
        className="abc-minimap-agent-icon"
        x={iconX}
        y={iconY}
        width={iconSize}
        height={iconSize}
        rx={iconSize * 0.3}
      />}
      {!isLlm && (isExternal ? (
        <>
          <circle
            className="abc-minimap-icon-mark"
            cx={iconX + iconSize / 2}
            cy={iconY + iconSize / 2}
            r={iconSize * 0.24}
          />
          <line
            className="abc-minimap-icon-mark"
            x1={iconX + iconSize / 2}
            x2={iconX + iconSize / 2}
            y1={iconY + iconSize * 0.27}
            y2={iconY + iconSize * 0.73}
          />
        </>
      ) : (
        <>
          <rect
            className="abc-minimap-icon-mark"
            x={iconX + iconSize * 0.27}
            y={iconY + iconSize * 0.32}
            width={iconSize * 0.46}
            height={iconSize * 0.38}
            rx={iconSize * 0.08}
          />
          <circle
            className="abc-minimap-icon-eye"
            cx={iconX + iconSize * 0.41}
            cy={iconY + iconSize * 0.5}
            r={Math.max(1, iconSize * 0.035)}
          />
          <circle
            className="abc-minimap-icon-eye"
            cx={iconX + iconSize * 0.59}
            cy={iconY + iconSize * 0.5}
            r={Math.max(1, iconSize * 0.035)}
          />
        </>
      ))}
      <rect
        className="abc-minimap-copy-line is-primary"
        x={textX}
        y={y + height * 0.31}
        width={textWidth * 0.76}
        height={lineHeight}
        rx={lineHeight / 2}
      />
      <rect
        className="abc-minimap-copy-line"
        x={textX}
        y={y + height * 0.57}
        width={textWidth * 0.54}
        height={lineHeight}
        rx={lineHeight / 2}
      />
    </g>
  );
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

function AgentBuildCanvasInner({
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
  const initialGraph = useMemo(
    () => buildCanvasGraph(draft, direction, readOnly),
    [],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(
    initialGraph.nodes,
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialGraph.edges);
  const nodesInitialized = useNodesInitialized();
  const lastStructure = useRef(
    `${direction}:${readOnly ? "readonly" : "editable"}:${structureKey(draft)}`,
  );
  const canvasRef = useRef<HTMLDivElement>(null);
  const fitFrameRef = useRef<number | null>(null);
  const { fitView } = useReactFlow<CanvasNode, CanvasEdge>();
  const currentGraph = useMemo(
    () => buildCanvasGraph(draft, direction, readOnly),
    [direction, draft, readOnly],
  );
  const [compactCanvas, setCompactCanvas] = useState(() =>
    window.matchMedia("(max-width: 860px)").matches,
  );
  const fitOptions = useMemo(
    () =>
      readOnly
        ? { padding: 0.16, minZoom: 0.05, maxZoom: 0.9 }
        : compactCanvas
        ? { padding: 0.08, minZoom: 0.35, maxZoom: 0.9 }
        : { padding: 0.14, minZoom: 0.42, maxZoom: 1.1 },
    [compactCanvas, readOnly],
  );
  const cancelScheduledFit = useCallback(() => {
    if (fitFrameRef.current === null) return;
    window.cancelAnimationFrame(fitFrameRef.current);
    fitFrameRef.current = null;
  }, []);
  const fitAfterLayout = useCallback((attempt = 0) => {
    cancelScheduledFit();
    fitFrameRef.current = window.requestAnimationFrame(() => {
      fitFrameRef.current = null;
      const container = canvasRef.current;
      if (
        container &&
        (container.clientWidth === 0 || container.clientHeight === 0) &&
        attempt < 8
      ) {
        fitAfterLayout(attempt + 1);
        return;
      }
      void fitView(fitOptions);
    });
  }, [cancelScheduledFit, fitOptions, fitView]);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 860px)");
    const handleChange = (event: MediaQueryListEvent) =>
      setCompactCanvas(event.matches);
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    const nextStructure = `${direction}:${
      readOnly ? "readonly" : "editable"
    }:${structureKey(draft)}`;
    const structureChanged = nextStructure !== lastStructure.current;
    lastStructure.current = nextStructure;
    setEdges(currentGraph.edges);
    setNodes((current) => {
      const currentNodes = new Map(
        current.map((node) => [node.id, node] as const),
      );
      return currentGraph.nodes.map((node) => {
        const currentNode = currentNodes.get(node.id);
        return {
          ...node,
          measured:
            !structureChanged &&
            currentNode &&
            currentNode.type === node.type
              ? currentNode.measured
              : undefined,
          position:
            !structureChanged && currentNode
              ? currentNode.position
              : node.position,
          selected:
            node.data.kind === "agent" &&
            !!node.data.path &&
            samePath(node.data.path, selectedPath),
        };
      });
    });
    if (structureChanged) {
      fitAfterLayout();
    }
  }, [currentGraph, draft, fitAfterLayout, selectedPath, setEdges, setNodes]);

  useEffect(() => {
    fitAfterLayout();
  }, [compactCanvas, fitAfterLayout]);

  useEffect(() => {
    if (!nodesInitialized) return;
    fitAfterLayout();
  }, [currentGraph, fitAfterLayout, nodesInitialized]);

  useEffect(() => {
    const container = canvasRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => fitAfterLayout());
    observer.observe(container);
    fitAfterLayout();
    return () => {
      observer.disconnect();
      cancelScheduledFit();
    };
  }, [cancelScheduledFit, fitAfterLayout]);

  const canvasActions = useMemo(
    () =>
      readOnly ? null : { onAdd, onInsert, onDelete },
    [onAdd, onDelete, onInsert, readOnly],
  );
  return (
    <CanvasDirectionContext.Provider value={direction}>
    <CanvasActionsContext.Provider value={canvasActions}>
    <section
      className={`abc-root is-${direction}${readOnly ? " is-readonly" : ""}`}
      aria-label={readOnly ? "只读 Agent 执行画布" : "Agent 执行画布"}
    >
      <div ref={canvasRef} className="abc-canvas">
        <ReactFlow<CanvasNode, CanvasEdge>
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => {
            if (!readOnly && node.data.kind === "agent" && node.data.path) {
              onSelect(node.data.path);
            }
          }}
          nodesDraggable={!readOnly}
          nodesConnectable={false}
          nodesFocusable={!readOnly}
          elementsSelectable={!readOnly}
          edgesFocusable={false}
          edgesReconnectable={false}
          panOnDrag={!readOnly || interactivePreview}
          zoomOnDoubleClick={interactivePreview}
          zoomOnPinch={!readOnly || interactivePreview}
          zoomOnScroll={!readOnly || interactivePreview}
          fitView
          fitViewOptions={fitOptions}
          onInit={() => fitAfterLayout()}
          minZoom={readOnly ? 0.05 : 0.35}
          maxZoom={1.6}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={18} size={2} color="#D8D8D8" />
          {(!readOnly || interactivePreview) && (
            <Controls showInteractive={false} />
          )}
          {MINIMAP_ENABLED && (
            <MiniMap
              pannable
              zoomable
              position="top-left"
              className="abc-minimap"
              ariaLabel="执行流程缩略图"
              bgColor="hsl(var(--panel))"
              maskColor="hsl(var(--muted) / 0.46)"
              maskStrokeColor="hsl(var(--primary) / 0.5)"
              maskStrokeWidth={1.5}
              nodeComponent={CanvasMiniMapNode}
              nodeClassName={(node) =>
                [
                  "abc-minimap-node",
                  node.type === "group"
                    ? "abc-minimap-node-group"
                    : node.data.kind === "terminal"
                      ? "abc-minimap-node-terminal"
                      : "abc-minimap-node-agent",
                  node.data.pattern ? `is-${node.data.pattern}` : "",
                ]
                  .filter(Boolean)
                  .join(" ")
              }
            />
          )}
        </ReactFlow>
      </div>
    </section>
    </CanvasActionsContext.Provider>
    </CanvasDirectionContext.Provider>
  );
}

export function AgentBuildCanvas(props: AgentBuildCanvasProps) {
  return (
    <ReactFlowProvider>
      <AgentBuildCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
