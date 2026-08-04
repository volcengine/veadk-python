# Multimodal Agent

This demo uses the VeADK frontend's multimodal pipeline to analyze images,
TXT/Markdown documents, PDFs, and videos, and mounts the `image_generate` and
`video_generate` tools. The frontend uploads files, `MultimodalMediaPlugin`
resolves them into Google GenAI Parts, and `doubao-seed-2-1-pro-260628` analyzes
them. Image or video creation requests call the corresponding tool.

## Run

From the repository root:

```bash
cp examples/multimodal_agent/.env.example .env
uv run veadk frontend --agents-dir examples --dev
```

Open <http://127.0.0.1:8000>, select `multimodal_agent`, then use the `+` button
in the composer to upload one or more files.

Example prompts:

- Image: `Describe the scene and extract all visible text.`
- TXT/Markdown: `Summarize this document into five actionable points.`
- PDF: `Explain the main argument and list the supporting evidence.`
- Video: `Give me a timeline of the important events in this video.`
- Mixed files: `Compare these files and identify any contradictions.`
- Image generation: `Create a cinematic image of Shanghai on a rainy night.`
- Video generation: `Create a time-lapse video of sunrise over the ocean.`

The Agent explicitly uses VeADK's default 2.1 Pro model. The generation tools
fall back to `MODEL_AGENT_API_KEY`; set `MODEL_IMAGE_API_KEY` and
`MODEL_VIDEO_API_KEY` to override them independently. Local uploads are stored
under `/tmp/veadk-media` by default; configure TOS for durable storage. PDFs
are automatically rendered to page images before the model call, with no extra
dependency or Agent callback required.
