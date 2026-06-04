import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Bot,
  Plus,
  GripVertical,
  Trash2,
  ArrowRightLeft,
  Repeat,
  ListOrdered,
  Sparkles,
} from "lucide-react";
import { type CreateModeProps, type AgentDraft, emptyDraft } from "./types";
import "./WorkflowCreate.css";

/* ------------------------------------------------------------------ *
 * Each canvas node carries a full AgentDraft in its data. The node id
 * doubles as the workflow node id when we assemble the final draft.
 * ------------------------------------------------------------------ */
type WfNodeData = {
  agent: AgentDraft;
};
type WfNode = Node<WfNodeData>;

type WorkflowType = "sequential" | "parallel" | "loop";

const WF_TYPES: {
  type: WorkflowType;
  label: string;
  desc: string;
  Icon: typeof ListOrdered;
}[] = [
  { type: "sequential", label: "顺序", desc: "节点依次执行", Icon: ListOrdered },
  { type: "parallel", label: "并行", desc: "节点同时执行", Icon: ArrowRightLeft },
  { type: "loop", label: "循环", desc: "节点循环执行", Icon: Repeat },
];

let nodeSeq = 0;
function nextNodeId() {
  nodeSeq += 1;
  return `node_${nodeSeq}`;
}

function makeAgentNode(
  id: string,
  position: { x: number; y: number },
  agent?: Partial<AgentDraft>,
): WfNode {
  const base = emptyDraft();
  return {
    id,
    type: "agentNode",
    position,
    data: {
      agent: {
        ...base,
        name: agent?.name ?? `agent_${id.replace("node_", "")}`,
        ...agent,
      },
    },
  };
}

/* ------------------------------------------------------------------ *
 * Custom React Flow node — a light, bordered card matching the shadcn
 * aesthetic. Selection is reflected via the `selected` prop.
 * ------------------------------------------------------------------ */
function AgentNode({ data, selected }: NodeProps<WfNode>) {
  const agent = data.agent;
  return (
    <div className={`wfb-node ${selected ? "wfb-node--selected" : ""}`}>
      <Handle type="target" position={Position.Left} className="wfb-handle" />
      <div className="wfb-node-icon">
        <Bot className="icon" />
      </div>
      <div className="wfb-node-body">
        <div className="wfb-node-name">{agent.name || "未命名节点"}</div>
        <div className="wfb-node-desc">
          {agent.instruction ? agent.instruction.slice(0, 48) : "点击编辑指令…"}
        </div>
      </div>
      <Handle type="source" position={Position.Right} className="wfb-handle" />
    </div>
  );
}

const nodeTypes = { agentNode: AgentNode };

const defaultEdgeOptions = {
  type: "smoothstep" as const,
  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
};

function WorkflowCreateInner({ onBack, onCreate }: CreateModeProps) {
  const rfInstance = useRef<ReactFlowInstance<WfNode, Edge> | null>(null);

  const [wfName, setWfName] = useState("");
  const [wfDesc, setWfDesc] = useState("");
  const [wfType, setWfType] = useState<WorkflowType>("sequential");

  // Start with a single node so the canvas isn't empty.
  const starter = useMemo(() => {
    nodeSeq = 0;
    const id = nextNodeId();
    return makeAgentNode(id, { x: 80, y: 120 }, { name: "agent_1" });
  }, []);

  const [nodes, setNodes, onNodesChange] = useNodesState<WfNode>([starter]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(starter.id);

  const selectedNode = nodes.find((n) => n.id === selectedId) ?? null;

  const onConnect = useCallback(
    (conn: Connection) =>
      setEdges((eds) => addEdge({ ...conn, ...defaultEdgeOptions }, eds)),
    [setEdges],
  );

  /* ---- add a node (button) ---- */
  const addNode = useCallback(() => {
    const id = nextNodeId();
    // Stagger placement so fresh nodes don't stack exactly.
    const offset = nodes.length * 28;
    const node = makeAgentNode(id, { x: 80 + offset, y: 120 + offset });
    setNodes((nds) => nds.concat(node));
    setSelectedId(id);
  }, [nodes.length, setNodes]);

  /* ---- drag from palette onto the canvas ---- */
  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData("application/wfb-node", "agentNode");
    e.dataTransfer.effectAllowed = "move";
  };

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      const kind = e.dataTransfer.getData("application/wfb-node");
      if (kind !== "agentNode" || !rfInstance.current) return;
      const position = rfInstance.current.screenToFlowPosition({
        x: e.clientX,
        y: e.clientY,
      });
      const id = nextNodeId();
      const node = makeAgentNode(id, position);
      setNodes((nds) => nds.concat(node));
      setSelectedId(id);
    },
    [setNodes],
  );

  /* ---- edit the selected node's agent fields ---- */
  const patchSelected = useCallback(
    (patch: Partial<AgentDraft>) => {
      if (!selectedId) return;
      setNodes((nds) =>
        nds.map((n) =>
          n.id === selectedId
            ? {
                ...n,
                data: { ...n.data, agent: { ...n.data.agent, ...patch } },
              }
            : n,
        ),
      );
    },
    [selectedId, setNodes],
  );

  const deleteSelected = useCallback(() => {
    if (!selectedId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setEdges((eds) =>
      eds.filter((e) => e.source !== selectedId && e.target !== selectedId),
    );
    setSelectedId(null);
  }, [selectedId, setNodes, setEdges]);

  /* ---- assemble the AgentDraft & finalize ---- */
  const handleCreate = useCallback(() => {
    const nodeAgents = nodes.map((n) => n.data.agent);
    const draft: AgentDraft = {
      ...emptyDraft(),
      name: wfName.trim() || "workflow_agent",
      description: wfDesc.trim(),
      instruction: wfDesc.trim(),
      subAgents: nodeAgents,
      workflow: {
        type: wfType,
        nodes: nodes.map((n) => ({ id: n.id, agent: n.data.agent })),
        edges: edges.map((e) => ({ from: e.source, to: e.target })),
      },
    };
    onCreate(draft);
  }, [nodes, edges, wfName, wfDesc, wfType, onCreate]);

  const canCreate = nodes.length > 0;

  // The app breadcrumb handles leaving this view, so onBack is no longer
  // rendered here.
  void onBack;

  return (
    <div className="wfb">
      <div className="wfb-grid">
        {/* ---------- left palette ---------- */}
        <aside className="wfb-palette">
          <div className="wfb-section-label">工作流信息</div>
          <label className="wfb-field">
            <span className="wfb-field-label">名称</span>
            <input
              className="wfb-input"
              value={wfName}
              onChange={(e) => setWfName(e.target.value)}
              placeholder="my_workflow"
            />
          </label>
          <label className="wfb-field">
            <span className="wfb-field-label">描述</span>
            <textarea
              className="wfb-input wfb-textarea"
              value={wfDesc}
              onChange={(e) => setWfDesc(e.target.value)}
              placeholder="这个工作流做什么…"
              rows={2}
            />
          </label>

          <div className="wfb-section-label">执行方式</div>
          <div className="wfb-types">
            {WF_TYPES.map(({ type, label, desc, Icon }) => (
              <button
                key={type}
                type="button"
                className={`wfb-type ${
                  wfType === type ? "wfb-type--active" : ""
                }`}
                onClick={() => setWfType(type)}
              >
                <Icon className="icon" />
                <span className="wfb-type-text">
                  <span className="wfb-type-name">{label}</span>
                  <span className="wfb-type-desc">{desc}</span>
                </span>
              </button>
            ))}
          </div>

          <div className="wfb-section-label">节点</div>
          <div
            className="wfb-palette-item"
            draggable
            onDragStart={onDragStart}
            title="拖拽到画布，或点击下方按钮添加"
          >
            <GripVertical className="icon wfb-grip" />
            <span className="wfb-node-icon wfb-node-icon--sm">
              <Bot className="icon" />
            </span>
            <span className="wfb-palette-item-text">Agent 节点</span>
          </div>
          <button className="wfb-add" type="button" onClick={addNode}>
            <Plus className="icon" />
            添加节点
          </button>

          <div className="wfb-hint">拖拽节点的圆点连线以表达执行顺序。</div>
        </aside>

        {/* ---------- canvas ---------- */}
        <div className="wfb-canvas">
          <button
            className="wfb-create"
            onClick={handleCreate}
            disabled={!canCreate}
            type="button"
          >
            <Sparkles className="icon" />
            创建工作流
          </button>
          <ReactFlow<WfNode, Edge>
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={(inst) => (rfInstance.current = inst)}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(null)}
            fitView
            fitViewOptions={{ padding: 0.3, maxZoom: 1 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} size={1} color="hsl(240 5.9% 88%)" />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable className="wfb-minimap" />
          </ReactFlow>
        </div>

        {/* ---------- right inspector ---------- */}
        <aside className="wfb-inspector">
          {selectedNode ? (
            <>
              <div className="wfb-inspector-head">
                <div className="wfb-section-label">节点配置</div>
                <button
                  className="wfb-icon-btn"
                  type="button"
                  onClick={deleteSelected}
                  title="删除节点"
                >
                  <Trash2 className="icon" />
                </button>
              </div>

              <label className="wfb-field">
                <span className="wfb-field-label">名称</span>
                <input
                  className="wfb-input"
                  value={selectedNode.data.agent.name}
                  onChange={(e) => patchSelected({ name: e.target.value })}
                  placeholder="agent_name"
                />
              </label>

              <label className="wfb-field">
                <span className="wfb-field-label">描述</span>
                <input
                  className="wfb-input"
                  value={selectedNode.data.agent.description}
                  onChange={(e) =>
                    patchSelected({ description: e.target.value })
                  }
                  placeholder="这个 agent 做什么…"
                />
              </label>

              <label className="wfb-field">
                <span className="wfb-field-label">指令 (instruction)</span>
                <textarea
                  className="wfb-input wfb-textarea"
                  value={selectedNode.data.agent.instruction}
                  onChange={(e) =>
                    patchSelected({ instruction: e.target.value })
                  }
                  placeholder="你是一个…"
                  rows={6}
                />
              </label>

              <label className="wfb-field">
                <span className="wfb-field-label">工具 (逗号分隔)</span>
                <input
                  className="wfb-input"
                  value={selectedNode.data.agent.tools.join(", ")}
                  onChange={(e) =>
                    patchSelected({
                      tools: e.target.value
                        .split(",")
                        .map((t) => t.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="web_search, calculator"
                />
              </label>

              <div className="wfb-inspector-meta">
                <span className="wfb-meta-key">节点 ID</span>
                <code className="wfb-meta-val">{selectedNode.id}</code>
              </div>
            </>
          ) : (
            <div className="wfb-inspector-empty">
              <Bot className="wfb-empty-icon" />
              <p>选择一个节点以编辑其配置</p>
              <p className="wfb-empty-sub">
                共 {nodes.length} 个节点 · {edges.length} 条连线
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

export function WorkflowCreate(props: CreateModeProps) {
  return (
    <ReactFlowProvider>
      <WorkflowCreateInner {...props} />
    </ReactFlowProvider>
  );
}
