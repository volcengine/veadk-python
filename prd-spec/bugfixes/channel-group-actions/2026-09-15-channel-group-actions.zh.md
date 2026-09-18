# 精简群权限操作

[English](2026-09-15-channel-group-actions.md)

日期：2026-09-15。状态：implemented。用户要求移除飞书群权限行的“编辑”，将“移除”替换为叉号图标。

## 证据、范围与设计
RuntimeChannels 将编辑和移除渲染为完整按钮，后代 span 规则还会拉伸按钮内部。去掉编辑，剩余操作复用仓库 SVG 叉号和可访问图标按钮，文本尺寸规则仅作用于行的直接标签。右侧保留 28px 点击区域，长群名在剩余空间换行。保留既有 DELETE/刷新、忙碌/错误行为及表单。不新增确认；当前处理没有确认。不改变 API、权限、状态/数据或后端契约，组件契约评估为无影响。

## 任务与验收
T-1/AC-1：无编辑入口，每群仅有一个叉号操作并带具体群名的可访问标签。T-2/AC-2：既有移除正常，长名称在窄窗口不挤走图标。T-3/AC-3：运行既有渠道/前端测试、构建/资源检查、模拟 API 的真实浏览器宽/窄检查。可逆展示调整不新增测试，移除处理保持不变。

## 评审与风险
直接评审（review-spec 不可用）：用户指令授权此范围，复用既有 SVG/按钮/语义变量，无行为或鉴权扩展。无阻塞。frontend/SPEC.md 引用的设计技能仍不可用。不执行云端/渠道操作或部署。验证完成。

## 验证结果
2026-09-15 当前未提交的群权限操作差异：pass。`cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1`：31 项；`npm --prefix frontend test`：1208 项；`npm --prefix frontend run build`：通过（既有包体积警告）；`npm --prefix frontend run test:webui-assets`：104 文件/248 引用。浏览器配隔离模拟 API：无编辑、28px 叉号、长群名在桌面及 480×1000 窄窗口布局正常；键盘 Enter 移除后显示 0 个群。初次模拟遗漏 Runtime DELETE 方法覆盖，修正模拟后通过，无需更改生产处理。范围内空白/双语链接检查通过。Python/IME/新增异步状态检查 not_applicable；真实云操作、部署和提交前门禁 not_run（未要求部署或提交）。T-1 至 T-3/AC-1 至 AC-3 完成，评审无阻塞。
