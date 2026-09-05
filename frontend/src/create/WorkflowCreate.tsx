import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";
import { useTranslation } from "react-i18next";
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
import { agentNameProblem, duplicateAgentNames } from "./agentNameValidation";
import { type CloudProvider } from "../adk/cloudProvider";
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
  Icon: typeof ListOrdered;
}[] = [
  { type: "sequential", Icon: ListOrdered },
  { type: "parallel", Icon: ArrowRightLeft },
  { type: "loop", Icon: Repeat },
];

let nodeSeq = 0;
function nextNodeId() {
  nodeSeq += 1;
  return `node_${nodeSeq}`;
}

function makeAgentNode(
  id: string,
  position: { x: number; y: number },
  cloudProvider: CloudProvider = "volcengine",
  agent?: Partial<AgentDraft>,
): WfNode {
  const base = emptyDraft(cloudProvider);
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
  const { t } = useTranslation("create");
  const agent = data.agent;
  return (
    <div className={`wfb-node ${selected ? "wfb-node--selected" : ""}`}>
      <Handle type="target" position={Position.Left} className="wfb-handle" />
      <div className="wfb-node-icon">
        <Bot className="icon" />
      </div>
      <div className="wfb-node-body">
        <div className="wfb-node-name">{agent.name || t("workflow.unnamedNode")}</div>
        <div className="wfb-node-desc">
          {agent.instruction ? agent.instruction.slice(0, 48) : t("workflow.editInstruction")}
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

function WorkflowCreateInner({
  cloudProvider = "volcengine",
  onBack,
  onCreate,
}: CreateModeProps) {
  const { t } = useTranslation("create");
  const rfInstance = useRef<ReactFlowInstance<WfNode, Edge> | null>(null);

  const [wfName, setWfName] = useState("");
  const [wfDesc, setWfDesc] = useState("");
  const [wfType, setWfType] = useState<WorkflowType>("sequential");

  // Start with a single node so the canvas isn't empty.
  const starter = useMemo(() => {
    nodeSeq = 0;
    const id = nextNodeId();
    return makeAgentNode(id, { x: 80, y: 120 }, cloudProvider, {
      name: "agent_1",
    });
  }, [cloudProvider]);

  const [nodes, setNodes, onNodesChange] = useNodesState<WfNode>([starter]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string | null>(starter.id);

  const selectedNode = nodes.find((n) => n.id === selectedId) ?? null;
  const effectiveWorkflowName = wfName.trim() || "workflow_agent";
  const duplicateNames = useMemo(
    () =>
      duplicateAgentNames({
        name: effectiveWorkflowName,
        subAgents: nodes.map((n) => n.data.agent),
      }),
    [effectiveWorkflowName, nodes],
  );
  const workflowNameProblem =
    agentNameProblem(effectiveWorkflowName, (key) => t(`validation.agentName.${key}`)) ??
    (duplicateNames.has(effectiveWorkflowName)
      ? t("workflow.errors.workflowNameUnique")
      : null);
  const selectedNameProblem = selectedNode
    ? agentNameProblem(selectedNode.data.agent.name, (key) => t(`validation.agentName.${key}`)) ??
      (duplicateNames.has(selectedNode.data.agent.name)
        ? t("workflow.errors.agentNameUnique")
        : null)
    : null;
  const canCreate =
    nodes.length > 0 &&
    workflowNameProblem === null &&
    nodes.every(
      (n) =>
        agentNameProblem(n.data.agent.name) === null &&
        !duplicateNames.has(n.data.agent.name),
    );

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
    const node = makeAgentNode(
      id,
      { x: 80 + offset, y: 120 + offset },
      cloudProvider,
    );
    setNodes((nds) => nds.concat(node));
    setSelectedId(id);
  }, [cloudProvider, nodes.length, setNodes]);

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
      const node = makeAgentNode(id, position, cloudProvider);
      setNodes((nds) => nds.concat(node));
      setSelectedId(id);
    },
    [cloudProvider, setNodes],
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
    if (!canCreate) return;
    const nodeAgents = nodes.map((n) => n.data.agent);
    const draft: AgentDraft = {
      ...emptyDraft(cloudProvider),
      name: effectiveWorkflowName,
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
  }, [
    canCreate,
    cloudProvider,
    nodes,
    edges,
    effectiveWorkflowName,
    wfDesc,
    wfType,
    onCreate,
  ]);

  // The app breadcrumb handles leaving this view, so onBack is no longer
  // rendered here.
  void onBack;

  return (
    <div className="wfb">
      <div className="wfb-grid">
        {/* ---------- left palette ---------- */}
        <aside className="wfb-palette">
            <div className="wfb-section-label">{t("workflow.sections.info")}</div>
          <label className="wfb-field">
              <span className="wfb-field-label">{t("common.name")}</span>
            <input
              className={`wfb-input ${workflowNameProblem ? "wfb-input--error" : ""}`}
              value={wfName}
              onChange={(e) => setWfName(e.target.value)}
              placeholder="my_workflow"
            />
            {workflowNameProblem && (
              <span className="wfb-field-error">{workflowNameProblem}</span>
            )}
          </label>
          <label className="wfb-field">
              <span className="wfb-field-label">{t("common.description")}</span>
            <textarea
              className="wfb-input wfb-textarea"
              value={wfDesc}
              onChange={(e) => setWfDesc(e.target.value)}
                placeholder={t("workflow.placeholders.description")}
              rows={2}
            />
          </label>

            <div className="wfb-section-label">{t("workflow.sections.execution")}</div>
          <div className="wfb-types">
              {WF_TYPES.map(({ type, Icon }) => (
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
                    <span className="wfb-type-name">{t(`workflow.types.${type}.label`)}</span>
                    <span className="wfb-type-desc">{t(`workflow.types.${type}.description`)}</span>
                </span>
              </button>
            ))}
          </div>

          <div className="wfb-section-label">{t("workflow.sections.nodes")}</div>
          <div
            className="wfb-palette-item"
            draggable
            onDragStart={onDragStart}
            title={t("workflow.dragHint")}
          >
            <GripVertical className="icon wfb-grip" />
            <span className="wfb-node-icon wfb-node-icon--sm">
              <Bot className="icon" />
            </span>
            <span className="wfb-palette-item-text">{t("workflow.agentNode")}</span>
          </div>
          <button className="wfb-add" type="button" onClick={addNode}>
            <Plus className="icon" />
            {t("workflow.addNode")}
          </button>

          <div className="wfb-hint">{t("workflow.connectHint")}</div>
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
            {t("workflow.create")}
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
            ariaLabelConfig={{
              "controls.ariaLabel": t("workflow.controls.ariaLabel"),
              "controls.zoomIn.ariaLabel": t("workflow.controls.zoomIn"),
              "controls.zoomOut.ariaLabel": t("workflow.controls.zoomOut"),
              "controls.fitView.ariaLabel": t("workflow.controls.fitView"),
            }}
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
                <div className="wfb-section-label">{t("workflow.sections.nodeConfig")}</div>
                <button
                  className="wfb-icon-btn"
                  type="button"
                  onClick={deleteSelected}
                  title={t("workflow.deleteNode")}
                >
                  <Trash2 className="icon" />
                </button>
              </div>

              <label className="wfb-field">
                <span className="wfb-field-label">{t("common.name")}</span>
                <input
                  className={`wfb-input ${selectedNameProblem ? "wfb-input--error" : ""}`}
                  value={selectedNode.data.agent.name}
                  onChange={(e) => patchSelected({ name: e.target.value })}
                  placeholder="agent_name"
                />
                {selectedNameProblem ? (
                  <span className="wfb-field-error">{selectedNameProblem}</span>
                ) : (
                  <span className="wfb-field-help">
                    {t("workflow.nameHelp")}
                  </span>
                )}
              </label>

              <label className="wfb-field">
                <span className="wfb-field-label">{t("common.description")}</span>
                <input
                  className="wfb-input"
                  value={selectedNode.data.agent.description}
                  onChange={(e) =>
                    patchSelected({ description: e.target.value })
                  }
                  placeholder={t("workflow.placeholders.agentDescription")}
                />
              </label>

              <label className="wfb-field">
                <span className="wfb-field-label">{t("workflow.instruction")}</span>
                <textarea
                  className="wfb-input wfb-textarea"
                  value={selectedNode.data.agent.instruction}
                  onChange={(e) =>
                    patchSelected({ instruction: e.target.value })
                  }
                  placeholder={t("workflow.placeholders.instruction")}
                  rows={6}
                />
              </label>

              <label className="wfb-field">
                <span className="wfb-field-label">{t("workflow.tools")}</span>
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
                <span className="wfb-meta-key">{t("workflow.nodeId")}</span>
                <code className="wfb-meta-val">{selectedNode.id}</code>
              </div>
            </>
          ) : (
            <div className="wfb-inspector-empty">
              <Bot className="wfb-empty-icon" />
              <p>{t("workflow.empty.selectNode")}</p>
              <p className="wfb-empty-sub">
                {t("workflow.empty.summary", { nodes: nodes.length, edges: edges.length })}
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
