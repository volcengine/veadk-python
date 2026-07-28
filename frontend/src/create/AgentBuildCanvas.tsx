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
import {
  ArrowRightLeft,
  Bot,
  Globe,
  ListOrdered,
  Plus,
  Repeat,
  Trash2,
} from "lucide-react";
import type { AgentDraft } from "./types";
import "@xyflow/react/dist/style.css";
import "./AgentBuildCanvas.css";

type NodePath = number[];
type AgentType = NonNullable<AgentDraft["agentType"]>;

const PATTERN_COPY: Record<
  AgentType,
  { label: string; description: string; icon: typeof Bot }
> = {
  llm: {
    label: "智能体",
    description: "理解任务并直接完成一个具体工作",
    icon: Bot,
  },
  sequential: {
    label: "分步协作",
    description: "内部步骤按照顺序依次执行",
    icon: ListOrdered,
  },
  parallel: {
    label: "同时处理",
    description: "内部步骤同时工作，完成后统一汇总",
    icon: ArrowRightLeft,
  },
  loop: {
    label: "循环执行",
    description: "重复执行内部步骤，直到满足停止条件",
    icon: Repeat,
  },
  a2a: {
    label: "远程智能体",
    description: "调用已经存在的远程 Agent",
    icon: Globe,
  },
};

type CanvasNodeData = {
  kind: "agent" | "terminal";
  path?: NodePath;
  agent?: AgentDraft;
  title: string;
  pattern?: AgentType;
  description?: string;
  childCount?: number;
  containedIn?: AgentType;
  layoutWidth?: number;
  layoutHeight?: number;
};

type CanvasNode = Node<CanvasNodeData>;

const NODE_WIDTH = 220;
const NODE_HEIGHT = 88;
const TERMINAL_WIDTH = 96;
const TERMINAL_HEIGHT = 34;
const GROUP_HEADER_HEIGHT = 64;
const GROUP_MIN_WIDTH = 310;
const GROUP_PADDING = 24;
const GROUP_BOUNDARY_PADDING = 56;
const GROUP_GAP = 40;
const GROUP_ADD_HEIGHT = 40;
const GROUP_ADD_GAP = 18;
const LOOP_EDGE_SPACE = 58;
const MINIMAP_ENABLED = false;

const isContainerType = (type: AgentType) =>
  type === "sequential" || type === "parallel" || type === "loop";

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
): { width: number; height: number } {
  const type = agent.agentType ?? "llm";
  if (!rendersAsGroup(agent, path)) {
    return { width: NODE_WIDTH, height: NODE_HEIGHT };
  }
  const sizes = agent.subAgents.map((child, index) =>
    measureAgent(child, [...path, index], direction),
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
  const bottomSpace = sizes.length
    ? type === "parallel"
      ? GROUP_ADD_GAP + GROUP_ADD_HEIGHT
      : type === "loop"
        ? LOOP_EDGE_SPACE
        : 0
    : GROUP_ADD_HEIGHT;
  if (!horizontalChildren) {
    return {
      width: Math.max(
        GROUP_MIN_WIDTH,
        widestChild + GROUP_PADDING * 2,
      ),
      height:
        GROUP_HEADER_HEIGHT +
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
      GROUP_HEADER_HEIGHT +
      GROUP_PADDING +
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
  },
): CanvasEdge {
  const edgeColor =
    options?.tone === "sequential"
      ? "hsl(213 40% 40%)"
      : options?.tone === "loop"
        ? "hsl(151 34% 34%)"
        : "hsl(220 9% 38%)";
  return {
    id: `${source}-${target}${options?.loop ? "-loop" : ""}`,
    source,
    target,
    sourceHandle: options?.loop ? "loop-source" : undefined,
    targetHandle: options?.loop ? "loop-target" : undefined,
    label,
    type: "insertStep",
    data: options
      ? {
          insert: options.insert,
          loop: options.loop,
          tone: options.tone,
        }
      : undefined,
    animated: options?.loop,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 16,
      height: 16,
      color: edgeColor,
    },
    style: {
      stroke: edgeColor,
      strokeWidth: 1.5,
    },
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
): {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
} {
  const nodes: CanvasNode[] = [
    {
      id: "terminal-input",
      type: "terminal",
      position: { x: 0, y: 0 },
      data: { kind: "terminal", title: "用户请求" },
      selectable: false,
      draggable: false,
    },
    {
      id: "terminal-output",
      type: "terminal",
      position: { x: 0, y: 0 },
      data: { kind: "terminal", title: "最终回复" },
      selectable: false,
      draggable: false,
    },
  ];
  const edges: CanvasEdge[] = [];

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
    nodes.push({
      id,
      type: "agent",
      parentId,
      extent: "parent",
      position,
      data: {
        kind: "agent",
        path,
        agent,
        title:
          type === "a2a"
            ? "远程智能体"
            : agent.name.trim() || (path.length === 0 ? "主 Agent" : "未命名步骤"),
        pattern: type,
        description: agent.description.trim() || PATTERN_COPY[type].description,
        childCount: agent.subAgents.length,
        containedIn,
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
    const id = pathId(path);
    const size = measureAgent(agent, path, direction);
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
        title:
          agent.name.trim() ||
          (path.length === 0 ? "主 Agent" : PATTERN_COPY[type].label),
        pattern: type,
        description: agent.description.trim() || PATTERN_COPY[type].description,
        childCount: agent.subAgents.length,
        containedIn,
        layoutWidth: size.width,
        layoutHeight: size.height,
      },
    });

    const childSizes = agent.subAgents.map((child, index) =>
      measureAgent(child, [...path, index], direction),
    );
    const flowPadding = childSizes.length && type !== "parallel"
      ? GROUP_BOUNDARY_PADDING
      : GROUP_PADDING;
    const horizontalChildren = direction === "horizontal"
      ? type !== "parallel"
      : type === "parallel";
    let cursor = flowPadding;
    const childIds = agent.subAgents.map((child, index) => {
      const childSize = childSizes[index];
      const childPosition =
        horizontalChildren
          ? {
              x: cursor,
              y: GROUP_HEADER_HEIGHT + GROUP_PADDING,
            }
          : {
              x: (size.width - childSize.width) / 2,
              y: GROUP_HEADER_HEIGHT + cursor,
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

    if (type === "sequential" || type === "loop") {
      for (let index = 0; index < childIds.length - 1; index += 1) {
        edges.push(
          makeEdge(childIds[index], childIds[index + 1], "然后", {
            tone: type,
            insert: { parentPath: path, index: index + 1 },
          }),
        );
      }
      if (type === "loop" && childIds.length > 1) {
        edges.push(
          makeEdge(childIds[childIds.length - 1], childIds[0], "继续循环", {
            loop: true,
            tone: "loop",
          }),
        );
      }
    }
    return id;
  }

  const addTopLevelNode = (agent: AgentDraft, path: NodePath): string[] => {
    const type = agent.agentType ?? "llm";
    const id = pathId(path);
    if (rendersAsGroup(agent, path)) {
      addGroupNode(agent, path);
      return [id];
    }
    nodes.push({
      id,
      type: "agent",
      position: { x: 0, y: 0 },
      data: {
        kind: "agent",
        path,
        agent,
        title:
          type === "a2a"
            ? "远程智能体"
            : agent.name.trim() || (path.length === 0 ? "主 Agent" : "未命名步骤"),
        pattern: type,
        description: agent.description.trim() || PATTERN_COPY[type].description,
        childCount: agent.subAgents.length,
      },
    });
    if (agent.subAgents.length === 0) return [id];

    const exits: string[] = [];
    agent.subAgents.forEach((child, index) => {
      const childPath = [...path, index];
      const childId = pathId(childPath);
      edges.push(
        makeEdge(id, childId, "调用", {
          insert: { parentPath: path, index },
        }),
      );
      exits.push(...addTopLevelNode(child, childPath));
    });
    return exits;
  };

  const rootId = pathId([]);
  const exits = addTopLevelNode(root, []);
  edges.push(makeEdge("terminal-input", rootId));
  exits.forEach((exitId) =>
    edges.push(makeEdge(exitId, "terminal-output")),
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
    ranksep: 50,
    nodesep: 34,
    edgesep: 14,
    marginx: 24,
    marginy: 24,
  });
  const topLevelIds = new Set(
    nodes.filter((node) => !node.parentId).map((node) => node.id),
  );
  nodes.filter((node) => !node.parentId).forEach((node) => {
    const terminal = node.data.kind === "terminal";
    graph.setNode(node.id, {
      width: terminal
        ? TERMINAL_WIDTH
        : node.data.layoutWidth ?? NODE_WIDTH,
      height: terminal
        ? TERMINAL_HEIGHT
        : node.data.layoutHeight ?? NODE_HEIGHT,
    });
  });
  edges
    .filter(
      (edge) => topLevelIds.has(edge.source) && topLevelIds.has(edge.target),
    )
    .forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);
  return {
    nodes: nodes.map((node) => {
      if (node.parentId) return node;
      const position = graph.node(node.id) as { x: number; y: number };
      const terminal = node.data.kind === "terminal";
      const width = terminal
        ? TERMINAL_WIDTH
        : node.data.layoutWidth ?? NODE_WIDTH;
      const height = terminal
        ? TERMINAL_HEIGHT
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
  const [edgePath, labelX, labelY] = getSmoothStepPath({
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

function AgentCanvasNode({ data, selected }: NodeProps<CanvasNode>) {
  const actions = useContext(CanvasActionsContext);
  const direction = useContext(CanvasDirectionContext);
  const targetPosition = direction === "vertical" ? Position.Top : Position.Left;
  const sourcePosition = direction === "vertical" ? Position.Bottom : Position.Right;
  const loopPosition = direction === "vertical" ? Position.Right : Position.Bottom;
  const type = data.pattern ?? "llm";
  const copy = PATTERN_COPY[type];
  const Icon = copy.icon;
  return (
    <div
      className={`abc-node is-${type}${
        data.containedIn ? ` is-contained-in-${data.containedIn}` : ""
      }${selected ? " is-selected" : ""}`}
    >
      <Handle type="target" position={targetPosition} className="abc-handle" />
      {type !== "llm" && (
        <span className="abc-node-icon"><Icon /></span>
      )}
      <span className="abc-node-copy">
        <span className="abc-node-meta">
          <span>{copy.label}</span>
        </span>
        <strong>{data.title}</strong>
        <small>{data.description}</small>
      </span>
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
  const addLabel =
    type === "llm"
      ? "添加子 Agent"
      : type === "parallel"
      ? "添加一个同时处理的步骤"
      : type === "loop"
        ? "添加循环步骤"
        : "添加下一个步骤";
  return (
    <div className={`abc-group is-${type}${selected ? " is-selected" : ""}`}>
      <Handle type="target" position={targetPosition} className="abc-handle" />
      <header className="abc-group-head">
        <span>
          <strong title={data.title}>{data.title}</strong>
          <small>{data.description}</small>
        </span>
      </header>
      {actions &&
        data.path !== undefined &&
        childCount > 0 &&
        type !== "parallel" && (
        <div className="abc-group-boundary-actions">
          <button
            type="button"
            className="abc-group-boundary-add is-start nodrag nopan"
            aria-label="添加到最前"
            title="添加到最前"
            onClick={(event) => {
              event.stopPropagation();
              actions.onInsert(data.path!, 0);
            }}
          >
            <Plus />
          </button>
          <button
            type="button"
            className="abc-group-boundary-add is-end nodrag nopan"
            aria-label="添加到最后"
            title="添加到最后"
            onClick={(event) => {
              event.stopPropagation();
              actions.onAdd(data.path!);
            }}
          >
            <Plus />
          </button>
        </div>
      )}
      {actions &&
        data.path !== undefined &&
        childCount > 0 &&
        type === "parallel" && (
        <button
          type="button"
          className="abc-group-add abc-group-add-bottom nodrag nopan"
          onClick={(event) => {
            event.stopPropagation();
            actions.onAdd(data.path!);
          }}
        >
          <Plus />
          <span>{addLabel}</span>
        </button>
      )}
      {actions && data.path !== undefined && childCount === 0 && (
        <button
          type="button"
          className="abc-group-add abc-group-add-empty nodrag nopan"
          onClick={(event) => {
            event.stopPropagation();
            actions.onAdd(data.path!);
          }}
        >
          <Plus />
          <span>{addLabel}</span>
        </button>
      )}
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

function TerminalNode({ data }: NodeProps<CanvasNode>) {
  const direction = useContext(CanvasDirectionContext);
  return (
    <div className="abc-terminal">
      <Handle
        type="target"
        position={direction === "vertical" ? Position.Top : Position.Left}
        className="abc-handle"
      />
      <span>{data.title}</span>
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
  direction = "horizontal",
}: AgentBuildCanvasProps) {
  const initialGraph = useMemo(() => buildCanvasGraph(draft, direction), []);
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(
    initialGraph.nodes,
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialGraph.edges);
  const nodesInitialized = useNodesInitialized();
  const lastStructure = useRef(`${direction}:${structureKey(draft)}`);
  const canvasRef = useRef<HTMLDivElement>(null);
  const { fitView } = useReactFlow<CanvasNode, CanvasEdge>();
  const currentGraph = useMemo(
    () => buildCanvasGraph(draft, direction),
    [direction, draft],
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
  const fitAfterLayout = useCallback(() => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => void fitView(fitOptions));
    });
  }, [fitOptions, fitView]);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 860px)");
    const handleChange = (event: MediaQueryListEvent) =>
      setCompactCanvas(event.matches);
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    const nextStructure = `${direction}:${structureKey(draft)}`;
    const structureChanged = nextStructure !== lastStructure.current;
    lastStructure.current = nextStructure;
    setEdges(currentGraph.edges);
    setNodes((current) => {
      const currentPositions = new Map(
        current.map((node) => [node.id, node.position] as const),
      );
      return currentGraph.nodes.map((node) => ({
        ...node,
        position:
          !structureChanged && currentPositions.get(node.id)
            ? currentPositions.get(node.id)!
            : node.position,
        selected:
          node.data.kind === "agent" &&
          !!node.data.path &&
          samePath(node.data.path, selectedPath),
      }));
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
    if (!readOnly || !canvasRef.current) return;
    const observer = new ResizeObserver(() => fitAfterLayout());
    observer.observe(canvasRef.current);
    fitAfterLayout();
    return () => observer.disconnect();
  }, [fitAfterLayout, readOnly]);

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
          minZoom={readOnly ? 0.05 : 0.35}
          maxZoom={1.6}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1.2} color="hsl(34 20% 82%)" />
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
