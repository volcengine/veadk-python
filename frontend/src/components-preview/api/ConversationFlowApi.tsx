const messages = [
  ["id / role", "string / user | assistant | system", "稳定标识和消息角色，追加流式内容时保持 id 不变"],
  ["blocks", "ConversationBlock[]", "按发生顺序排列的内容；同一条用户消息的文字、附件和媒体共用一个气泡；提供后覆盖旧的 content / steps"],
  ["name", "string", "消息的无障碍名称，仅供读屏识别，不在界面显示；不提供头像属性"],
  ["status", "pending | running | complete | error | cancelled", "助手执行状态，由业务控制"],
  ["startedAt / endedAt", "number", "执行开始与结束的 Unix 时间戳，单位毫秒；running 期间按 startedAt 实时计时，无新事件也更新；endedAt 固定结束时间"],
  ["durationMs", "number", "执行耗时，单位毫秒；完成、失败或取消后的最终值优先于时间戳；运行中未提供 startedAt 时，以首次观察到的状态和已耗时为起点继续计时"],
  ["ttftMs", "number", "首个 token 耗时，单位毫秒；由业务在首个 token 到达时提供，不随执行时钟递增；未提供不显示"],
  ["tokens / model", "number / string", "总 token 数和模型名称，不在组件内估算"],
  ["error", "ReactNode", "当前回复的错误说明，保留此前已生成内容"],
  ["copyText", "string", "覆盖默认复制文本；默认复制 Markdown 内容"],
  ["feedback / actions", "like | dislike | null / ReactNode", "受控反馈；actions 可替换整个操作组，包括 Menu 等任意组件，null 隐藏"],
];
const blocks = [
  ["markdown", "id, text", "Markdown 正文，代码、表格和图表自动分流到对应组件"],
  ["reasoning", "id, title, content, status?, startedAt?, endedAt?, durationMs?, defaultOpen?", "思考或执行摘要，可折叠；running 时独立计时，不会自行生成或推断过程内容"],
  ["tool", "id, title, input?, output?, result?, error?", "工具输入和输出为字符串，可单独折叠；inputLanguage / outputLanguage 默认 json；result 支持自定义结果组件"],
  ["handoff", "id, title, fromAgent?, toAgent, status, steps?, content?", "显示移交关系、子智能体状态及内部步骤；支持 startedAt / endedAt / durationMs / defaultOpen，嵌套步骤各自计时"],
  ["plan", "id, title, items: { id, title, status }[]", "按需传入执行计划及各项状态，当前对话流示例未启用"],
  ["visualization", "id, kind: echarts | mermaid, source, title?", "复用 InfoCard 展示真实图表，支持源码切换、放大查看；未完成源码在运行中保留，错误可查看原文"],
  ["media", "id, kind: image | video | audio, src, alt?, name?, poster?, caption?", "直接展示图片、视频或音频；图片复用 ModalButton 放大，视频与音频使用原生控制条，不自动播放；支持 onPreview / onDownload，加载失败复用 ErrorState"],
  ["files", "id, title?, files: ConversationFile[]", "文件支持 id / name / description / href / preview / onPreview / onDownload，预览内容按需挂载"],
  ["authorization", "id, title, description?, status, onAuthorize?, onCancel?", "授权按钮触发业务回调，授权成功、失败与取消由业务更新状态"],
  ["custom", "id, title?, content: ReactNode", "承载 A2UI、部署交付、引用、媒体或其他领域组件"],
];

export function ConversationFlowApi() {
  return <>
    <section aria-label="ConversationMessage 数据字段">
      <h3>ConversationMessage 数据字段</h3>
      <p>用户消息靠右，模型回复靠左；同一条 prompt 的文字和富内容合并展示。消息区域复用固定高度 ScrollArea，默认 600px，可通过 height 和 scrollAreaProps 配置，不包含输入框</p>
      <div className="component-api__scroll"><table><thead><tr><th>字段</th><th>类型</th><th>说明</th></tr></thead><tbody>{messages.map(row => <tr key={row[0]}>{row.map((cell, index) => index ? <td key={index}>{cell}</td> : <th key={index} scope="row">{cell}</th>)}</tr>)}</tbody></table></div>
    </section>
    <section aria-label="ConversationBlock 内容类型">
      <h3>ConversationBlock 内容类型</h3>
      <p>reasoning、tool 和 handoff 共用 startedAt、endedAt、durationMs 计时字段；单位与消息一致。完成、失败或取消后冻结耗时；同一 id 重试时传入新的 startedAt 并清除上次 endedAt / durationMs</p>
      <div className="component-api__scroll"><table><thead><tr><th>type</th><th>字段</th><th>行为</th></tr></thead><tbody>{blocks.map(row => <tr key={row[0]}>{row.map((cell, index) => index ? <td key={index}>{cell}</td> : <th key={index} scope="row">{cell}</th>)}</tr>)}</tbody></table></div>
    </section>
    <section aria-label="Studio 数据适配">
      <h3>Studio 数据适配</h3>
      <p>fromStudioTurns(turns, options) 接收现有 Studio Turn 数组，保留所有消息块的顺序，覆盖思考、工具、执行计划、移交、附件、产物、项目交付、技能调用、授权与 A2UI；图片、视频与音频附件直接显示，混合附件保持原始顺序</p>
      <div className="component-api__scroll"><table><thead><tr><th>参数</th><th>行为</th></tr></thead><tbody>
        <tr><th scope="row">renderBlock(block, turn)</th><td>覆盖领域渲染；undefined 使用默认展示，null 隐藏，其他 React 内容直接渲染</td></tr>
        <tr><th scope="row">onSurfaceAction</th><td>返回 A2UI action 与 node；支持当前 Text / Icon / Row / Column / Card / Divider / Button 目录，未知节点显示可展开的源码</td></tr>
        <tr><th scope="row">onAuthorize / onCancelAuthorization</th><td>返回授权消息，交给业务完成授权流程</td></tr>
        <tr><th scope="row">onArtifactPreview / onArtifactDownload</th><td>返回产物文件名称和版本</td></tr>
        <tr><th scope="row">resolveArtifactMedia(file, turn)</th><td>返回已取得的媒体地址 src，以及可选 kind、mimeType、alt、poster、caption；图片、视频、音频产物直接展示，未提供地址时保留文件预览入口</td></tr>
        <tr><th scope="row">onAttachmentPreview / onAttachmentDownload</th><td>返回原始附件，支持应用特定的地址解析</td></tr>
        <tr><th scope="row">onDeliveryDownload / onDeliveryDeploy</th><td>返回项目交付对象，交给业务执行下载或部署</td></tr>
      </tbody></table></div>
    </section>
  </>;
}
