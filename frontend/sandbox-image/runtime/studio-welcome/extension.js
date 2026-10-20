const vscode = require('vscode');
const crypto = require('node:crypto');
const {initializeTerminals, openTerminals} = require('./terminals');
const zh = !/^en(?:-|$)/i.test(process.env.VSCODE_LANG || 'zh-CN');
const t = (cn, en) => zh ? cn : en;
let panel;
function show() {
  if (panel) { panel.reveal(); return; }
  panel = vscode.window.createWebviewPanel('studio.welcome', t('欢迎使用 AgentKit Studio','Welcome to AgentKit Studio'), vscode.ViewColumn.One, {retainContextWhenHidden:true});
  panel.onDidDispose(() => { panel = undefined; });
  const nonce = crypto.randomBytes(18).toString('base64');
  const docs = zh ? 'https://www.volcengine.com/docs/86681' : 'https://docs.byteplus.com/en/docs/agentkit';
  panel.webview.html = `<!doctype html><html lang="${zh?'zh-CN':'en'}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}';"><style nonce="${nonce}">
  *{box-sizing:border-box}body{margin:0;background:var(--vscode-editor-background);color:var(--vscode-foreground);font:13px/1.8 var(--vscode-font-family);--muted:var(--vscode-descriptionForeground);--border:var(--vscode-widget-border,var(--vscode-panel-border));--accent:var(--vscode-textLink-foreground)}
  main{max-width:800px;padding:54px 40px 40px;margin:auto}header{padding-bottom:32px;border-bottom:1px solid var(--border)}h1{font-size:26px;line-height:1.45;font-weight:600;margin:0;letter-spacing:-.3px}section{margin-top:30px}h2{font-size:15px;font-weight:600;line-height:1.5;margin:0 0 13px}p{margin:0;color:var(--muted);max-width:660px}.links{display:flex;flex-wrap:wrap;gap:10px}.links a{display:inline-flex;align-items:center;gap:12px;border:1px solid var(--border);border-radius:6px;padding:8px 14px;color:var(--accent);text-decoration:none;transition:background 150ms,border-color 150ms}.links a:hover{background:var(--vscode-list-hoverBackground);border-color:var(--accent)}a:focus-visible{outline:2px solid var(--vscode-focusBorder);outline-offset:3px}.links svg{width:14px;height:14px}.intro{padding-top:26px;border-top:1px solid var(--border)}@media(max-width:520px){main{padding:30px 22px}h1{font-size:22px}.links{gap:8px}}@media(prefers-reduced-motion:reduce){*{transition:none!important}}
  </style></head><body><main><header><h1>${t('欢迎使用 AgentKit Studio','Welcome to AgentKit Studio')}</h1></header>
  <section><h2>${t('常用链接','Useful links')}</h2><div class="links">${[
    ['https://volcengine.github.io/veadk-python/',t('VeADK 文档','VeADK documentation')],
    [docs,t('AgentKit 文档','AgentKit documentation')],
    ['https://github.com/volcengine/veadk-python',t('VeADK 开源仓库','VeADK on GitHub')]
  ].map(([url,label])=>`<a href="${url}">${label}<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><path d="M4 12 12 4M4 4h8v8"/></svg></a>`).join('')}</div></section>
  <section class="intro"><h2>VeADK</h2><p>${t('VeADK 是面向 AI Agent 开发的开源 Python 框架，提供模型调用、工具集成、记忆管理与工作流编排等能力，帮助你从几行代码开始构建 Agent，并逐步完成调试、评估和部署。','VeADK is an open-source Python framework for building AI Agents. It brings together models, tools, memory and workflows, helping you move from a few lines of code to debugging, evaluation and deployment.')}</p></section>
  <section class="intro"><h2>AgentKit</h2><p>${t('AgentKit 是火山引擎面向 AI Agent 的云平台，为 Agent 提供运行环境、开发工具和配套云服务，帮助团队将本地开发的 Agent 部署到云端，并持续运行和管理。','AgentKit is BytePlus’s cloud platform for AI Agents. It provides runtime environments, development tools and supporting cloud services to help teams deploy, run and manage Agents in the cloud.')}</p></section>
  </main></body></html>`;
}
async function activate(context) {
  await initializeTerminals(vscode, context.workspaceState);
  context.subscriptions.push(vscode.commands.registerCommand('studio.openTerminals', () => openTerminals(vscode)));
  context.subscriptions.push(vscode.commands.registerCommand('studio.welcome',show));
  if(vscode.workspace.getConfiguration('studio').get('showWelcomeOnStartup',true)) {
    const oldWelcomeTabs = vscode.window.tabGroups.all.flatMap(group => group.tabs)
      .filter(tab => tab.input instanceof vscode.TabInputWebview && tab.input.viewType.endsWith('studio.welcome'));
    if (oldWelcomeTabs.length) await vscode.window.tabGroups.close(oldWelcomeTabs, true);
    show();
  }
}
module.exports = {activate};
