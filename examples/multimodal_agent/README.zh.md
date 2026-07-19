# 多模态 Agent

这个 Demo 使用 VeADK frontend 的多模态链路分析图片、TXT/Markdown、PDF
和视频，并挂载 `image_generate` 与 `video_generate` 工具。frontend 负责上传
文件，`MultimodalMediaPlugin` 将文件还原为 Google GenAI Parts，再交给
`doubao-seed-2-1-pro-260628` 分析；生成图片或视频时则调用对应工具。

## 运行

在仓库根目录执行：

```bash
cp examples/multimodal_agent/.env.example .env
uv run veadk frontend --agents-dir examples --dev
```

打开 <http://127.0.0.1:8000>，选择 `multimodal_agent`，然后通过输入框中的
`+` 按钮上传一个或多个文件。

示例问题：

- 图片：`描述画面，并提取所有可见文字。`
- TXT/Markdown：`把这份文档总结成五条可执行建议。`
- PDF：`解释核心观点，并列出支撑证据。`
- 视频：`按时间线总结视频中的重要事件。`
- 混合文件：`比较这些文件，并找出相互矛盾的地方。`
- 图片生成：`生成一张雨夜上海街头的电影感图片。`
- 视频生成：`生成一段海边日出的延时摄影视频。`

Agent 明确使用 VeADK 默认的 2.1 Pro 模型。图片与视频生成工具默认复用
`MODEL_AGENT_API_KEY`；也可以分别设置 `MODEL_IMAGE_API_KEY` 和
`MODEL_VIDEO_API_KEY`。本地上传默认保存在 `/tmp/veadk-media`；需要持久化时
请配置 TOS。PDF 会在调用模型前自动渲染为页面图片，无需安装额外依赖或配置
Agent callback。
