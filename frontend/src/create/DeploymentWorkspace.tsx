import { useState, type ReactNode } from "react";
import feishuIcon from "./assets/create-workspace/feishu.svg";
import dingtalkIcon from "./assets/create-workspace/dingtalk.svg";
import wecomIcon from "./assets/create-workspace/wecom.svg";
import slackIcon from "./assets/create-workspace/slack.svg";
import { CreateNavbar } from "./CreateNavbar";
import { CreationFlowCanvas } from "./CreationFlowCanvas";
import "./DeploymentWorkspace.css";

interface DeploymentWorkspaceProps {
  onBack: () => void;
}

const INVOKE_URL = "https://agentkit.example.volceapi.com/run_sse";
const MASKED_API_KEY = "····················";

const CHANNELS = [
  { label: "飞书", icon: feishuIcon },
  { label: "钉钉", icon: dingtalkIcon },
  { label: "企业微信", icon: wecomIcon },
  { label: "Slack", icon: slackIcon },
];

type IntegrationTab = "api" | "webhook" | "embed";

function CloseIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="m4.5 4.5 11 11M15.5 4.5l-11 11" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d="M5.5 4.5V3.25c0-.69.56-1.25 1.25-1.25h6c.69 0 1.25.56 1.25 1.25v6c0 .69-.56 1.25-1.25 1.25H11.5M3.25 5.5h6c.69 0 1.25.56 1.25 1.25v6c0 .69-.56 1.25-1.25 1.25h-6C2.56 14 2 13.44 2 12.75v-6c0-.69.56-1.25 1.25-1.25Z" />
    </svg>
  );
}

function CopyButton({ value, label }: { value: string; label: string }) {
  return (
    <button
      type="button"
      className="deployment-panel__copy"
      aria-label={label}
      onClick={() => void navigator.clipboard?.writeText(value)}
    >
      <CopyIcon />
    </button>
  );
}

function CodeLine({ number, children }: { number: number; children?: ReactNode }) {
  return (
    <div className="deployment-panel__code-line">
      <span className="deployment-panel__line-number">{number}</span>
      <code>{children}</code>
    </div>
  );
}

function InvocationExample() {
  return (
    <section className="deployment-panel__example" aria-label="调用示例">
      <header className="deployment-panel__example-header">
        <h3>调用示例</h3>
        <CopyButton value="private async waitAttachConnection(port: number)" label="复制调用示例" />
      </header>
      <div className="deployment-panel__code" aria-label="TypeScript 调用示例">
        <CodeLine number={1}><span className="token-keyword">private async</span> <span className="token-function">waitAttachConnection</span>(<span className="token-variable">port</span>: <span className="token-type">number</span>): <span className="token-type">Promise&lt;ICubePrepareLaunchResponse&gt;</span><span className="token-function">&#123;</span></CodeLine>
        <CodeLine number={2}>&nbsp;&nbsp;<span className="token-keyword">const</span> <span className="token-name">command</span> = <span className="token-string">'prepare-attach'</span>;</CodeLine>
        <CodeLine number={3}>&nbsp;&nbsp;<span className="token-keyword">const</span> <span className="token-name">attachPrepareRequest</span>: <span className="token-type">ICubePrepareAttachRequest</span> = &#123;</CodeLine>
        <CodeLine number={4}>&nbsp;&nbsp;&nbsp;&nbsp;seq: <span className="token-type">0</span>,</CodeLine>
        <CodeLine number={5}>&nbsp;&nbsp;&nbsp;&nbsp;command,</CodeLine>
        <CodeLine number={6}>&nbsp;&nbsp;&nbsp;&nbsp;type: <span className="token-string">'request'</span></CodeLine>
        <CodeLine number={7}>&nbsp;&nbsp;&nbsp;&nbsp;seq_id: <span className="token-name">websocketManager</span>.<span className="token-function">generateSeqId</span>(),</CodeLine>
        <CodeLine number={8}>&nbsp;&nbsp;&nbsp;&nbsp;arguments: <span className="token-type">ICubeDAProxyRequestArguments</span>,</CodeLine>
        <CodeLine number={9}>&nbsp;&nbsp;&#125;</CodeLine>
        <CodeLine number={10}>&nbsp;&nbsp;<span className="token-keyword">if</span> (<span className="token-variable">port</span>) &#123;</CodeLine>
        <CodeLine number={11}>&nbsp;&nbsp;&nbsp;&nbsp;<span className="token-name">attachPrepareRequest</span>.port = <span className="token-variable">port</span>;</CodeLine>
        <CodeLine number={12}>&nbsp;&nbsp;&#125;</CodeLine>
        <CodeLine number={13}>&nbsp;&nbsp;<span className="token-function">traceLog</span>(<span className="token-string">'Launcn response'</span>, <span className="token-name">attachPrepareRequest</span>);</CodeLine>
        <CodeLine number={14}>&nbsp;&nbsp;<span className="token-keyword">const</span> <span className="token-name">response</span> = <span className="token-keyword">await</span></CodeLine>
        <CodeLine number={15}>&nbsp;&nbsp;<span className="token-name">websocketManager</span>.<span className="token-function">sendRequest</span>&lt;<span className="token-type">ICubePrepareLaunchResponse</span>&gt;(<span className="token-name">attachPrepareRequest</span>)</CodeLine>
        <CodeLine number={16}>&nbsp;&nbsp;<span className="token-function">traceLog</span>(<span className="token-string">'Launcn response'</span>, <span className="token-name">response</span>);</CodeLine>
        <CodeLine number={17} />
        <CodeLine number={18}>&nbsp;&nbsp;<span className="token-keyword">return</span> <span className="token-name">response</span>;</CodeLine>
        <CodeLine number={19}><span className="token-function">&#125;</span></CodeLine>
        <CodeLine number={20} />
        <CodeLine number={21} />
      </div>
    </section>
  );
}

export function DeploymentWorkspace({ onBack }: DeploymentWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<IntegrationTab>("api");

  return (
    <section className="create-workspace create-workspace--deployment" aria-label="发布与集成工作台">
      <CreateNavbar mode="deploy" onBack={onBack} primaryLabel="发布" />

      <CreationFlowCanvas
        centerViewport
        selectedAgentId={null}
        configPanelOpen
        onAgentSelect={() => {}}
      />

      <aside className="deployment-panel" aria-labelledby="deployment-panel-title">
        <header className="deployment-panel__header">
          <h2 id="deployment-panel-title">发布与集成</h2>
          <button type="button" className="deployment-panel__close" onClick={onBack} aria-label="关闭发布与集成">
            <CloseIcon />
          </button>
        </header>

        <div className="deployment-panel__content">
          <section className="deployment-panel__channels" aria-labelledby="deployment-channels-title">
            <h3 id="deployment-channels-title">消息渠道</h3>
            <div className="deployment-panel__channel-list">
              {CHANNELS.map((channel) => (
                <button type="button" className="deployment-panel__channel" key={channel.label}>
                  <img src={channel.icon} alt="" />
                  <span>{channel.label}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="deployment-panel__integration" aria-labelledby="deployment-integration-title">
            <div className="deployment-panel__integration-heading">
              <h3 id="deployment-integration-title">企业系统集成</h3>
              <div className="deployment-panel__tabs" role="tablist" aria-label="企业系统集成方式">
                {([
                  ["api", "开放 api"],
                  ["webhook", "webhook 回调"],
                  ["embed", "网页嵌入"],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === value}
                    className={activeTab === value ? "is-active" : ""}
                    onClick={() => setActiveTab(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="deployment-panel__field">
              <span>调用地址</span>
              <div className="deployment-panel__value">
                <span>{INVOKE_URL}</span>
                <CopyButton value={INVOKE_URL} label="复制调用地址" />
              </div>
            </div>

            <div className="deployment-panel__field">
              <span>API Key</span>
              <div className="deployment-panel__value">
                <span>{MASKED_API_KEY}</span>
                <CopyButton value="" label="复制 API Key" />
              </div>
            </div>

            <InvocationExample />
          </section>
        </div>
      </aside>
    </section>
  );
}
