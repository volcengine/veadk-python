import { Button } from "../../components/primitives/Button";
import { Toast, ToastProvider, useToast, type ToastVariant } from "../../components/primitives/Toast";
import { ComponentApi } from "../api/ComponentApi";
import "./ToastPreview.css";

const variants: { variant: ToastVariant; label: string; title: string; description: string }[] = [
  { variant: "info", label: "提示", title: "配置已更新", description: "新的模型配置和工具权限将在下次运行时生效，当前正在执行的任务会继续使用原有设置。你可以前往详情页查看完整配置" },
  { variant: "success", label: "成功", title: "保存成功", description: "项目名称、描述和工作流配置已全部保存，团队成员现在可以查看最新版本。你可以继续编辑，也可以返回资源列表查看更新后的内容" },
  { variant: "warning", label: "警告", title: "尚有未保存的更改", description: "当前页面包含尚未保存的模型参数、工具配置和提示词内容。直接离开会丢失本次修改，请先保存配置，或确认不再需要这些更改" },
  { variant: "error", label: "错误", title: "保存失败", description: "连接服务器时发生错误，本次修改暂未保存。请检查网络连接和当前账号的访问权限后重试；你填写的内容仍然保留在页面中，无需重新输入" },
];

function ToastExamples() {
  const { add, dismiss } = useToast();

  function showAction() {
    const id = "toast-preview-action";
    add({
      id,
      variant: "success",
      title: "已移除资源",
      description: "可以撤销本次操作",
      duration: 0,
      action: <Button variant="secondary" onClick={() => {
        dismiss(id);
        add({ variant: "success", title: "已恢复资源" });
      }}>撤销</Button>,
    });
  }

  return <>
    <div className="toast-preview__triggers" role="group" aria-label="触发 Toast">
      {variants.map(({ variant, label, title, description }) => <Button key={variant} variant="secondary" onClick={() => add({ variant, title, description })}>{label}</Button>)}
      <Button variant="secondary" onClick={showAction}>带操作</Button>
      <Button variant="link" onClick={() => dismiss()}>全部关闭</Button>
    </div>
    <p className="toast-preview__hint">通知在顶部居中显示，间距 8px，4 秒后自动关闭；悬停或键盘聚焦时暂停，带操作示例保持显示</p>
    <div className="toast-preview__states" aria-label="Toast 样式">
      {variants.map(({ variant, title, description }) => <Toast key={variant} role="presentation" variant={variant} title={title} description={description} />)}
    </div>
  </>;
}

function ToastHookApi() {
  return <div className="component-api">
    <section aria-label="useToast 方法">
      <h3>useToast 方法</h3>
      <div className="component-api__scroll"><table>
        <thead><tr><th scope="col">方法</th><th scope="col">参数</th><th scope="col">返回值</th><th scope="col">说明</th></tr></thead>
        <tbody>
          <tr><th scope="row">add</th><td>ToastOptions</td><td>string</td><td>添加通知并返回 id；重复 id 更新原通知和计时</td></tr>
          <tr><th scope="row">dismiss</th><td>id?: string</td><td>void</td><td>关闭指定通知，不传 id 时关闭全部</td></tr>
        </tbody>
      </table></div>
    </section>
    <section aria-label="ToastOptions 参数与属性">
      <h3>ToastOptions 参数与属性</h3>
      <div className="component-api__scroll"><table>
        <thead><tr><th scope="col">参数 / 属性</th><th scope="col">类型</th><th scope="col">必填</th><th scope="col">默认值</th><th scope="col">说明</th></tr></thead>
        <tbody>
          <tr><th scope="row">id</th><td>string</td><td>否</td><td>自动生成</td><td>使用同一 id 更新通知</td></tr>
          <tr><th scope="row">title</th><td>ReactNode</td><td>否</td><td>未设置</td><td>主标题，title 与 description 至少提供一项</td></tr>
          <tr><th scope="row">description</th><td>ReactNode</td><td>否</td><td>未设置</td><td>说明文字，可以单独使用</td></tr>
          <tr><th scope="row">variant</th><td>info | success | warning | error</td><td>否</td><td>info</td><td>通知状态</td></tr>
          <tr><th scope="row">duration</th><td>number</td><td>否</td><td>继承 Provider</td><td>自动关闭时长，单位毫秒；0 表示保持显示</td></tr>
          <tr><th scope="row">action</th><td>ReactNode</td><td>否</td><td>未设置</td><td>操作区域，支持按钮、链接；关闭由操作回调调用 dismiss</td></tr>
          <tr><th scope="row">closeLabel</th><td>string</td><td>否</td><td>关闭通知</td><td>关闭按钮的无障碍名称</td></tr>
          <tr><th scope="row">onClose</th><td>() =&gt; void</td><td>否</td><td>未设置</td><td>通知关闭时触发</td></tr>
        </tbody>
      </table></div>
    </section>
  </div>;
}

export function ToastPreview() {
  return <section aria-labelledby="toast-preview-title">
    <h2 id="toast-preview-title" className="component-preview-title">Toast</h2>
    <ToastProvider><ToastExamples /></ToastProvider>
    <ComponentApi names={["Toast", "ToastProvider"]} />
    <ToastHookApi />
  </section>;
}
