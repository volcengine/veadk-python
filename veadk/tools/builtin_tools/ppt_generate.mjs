import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [, , inputPath, outputPath, previewPath] = process.argv;
if (!inputPath || !outputPath || !previewPath) {
  throw new Error("Usage: ppt_generate.mjs <input.json> <output.pptx> <preview.webp>");
}

async function saveBlob(output, blob) {
  await fs.writeFile(output, new Uint8Array(await blob.arrayBuffer()));
}

async function loadArtifactTool() {
  const configured = (process.env.VEADK_ARTIFACT_TOOL_PATH || "").trim();
  if (!configured) return import("@oai/artifact-tool");
  const modulePath = configured.endsWith(".mjs")
    ? configured
    : path.join(configured, "dist", "artifact_tool.mjs");
  return import(pathToFileURL(modulePath).href);
}

const themes = {
  blue: {
    canvas: "#F4F7FB",
    cover: "#0B1F3A",
    title: "#10233F",
    body: "#344760",
    muted: "#6B7C93",
    accent: "#2F6FED",
    coverText: "#FFFFFF",
    coverMuted: "#C9D8F0",
  },
  dark: {
    canvas: "#10151E",
    cover: "#090D14",
    title: "#F5F7FA",
    body: "#CCD4E0",
    muted: "#8D9AAF",
    accent: "#74A7FF",
    coverText: "#FFFFFF",
    coverMuted: "#AAB6C8",
  },
  warm: {
    canvas: "#FBF6EF",
    cover: "#41281E",
    title: "#3D2A24",
    body: "#604A42",
    muted: "#8C7469",
    accent: "#D66A3A",
    coverText: "#FFF8F2",
    coverMuted: "#E7CFC2",
  },
  green: {
    canvas: "#F2F8F5",
    cover: "#12372B",
    title: "#173B31",
    body: "#36594F",
    muted: "#6D887F",
    accent: "#2B8A68",
    coverText: "#F8FFFC",
    coverMuted: "#BFD9CF",
  },
};

function addText(slide, text, position, style) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = style;
  return shape;
}

function sourceNotes(slide, sources) {
  if (!Array.isArray(sources) || sources.length === 0) return;
  slide.speakerNotes.textFrame.setText(
    `[Sources]\n${sources.map((source) => `- ${source}`).join("\n")}`,
  );
}

const spec = JSON.parse(await fs.readFile(inputPath, "utf8"));
const { Presentation, PresentationFile } = await loadArtifactTool();
const theme = themes[spec.theme] || themes.blue;
const presentation = Presentation.create({
  slideSize: { width: 1280, height: 720 },
});

const cover = presentation.slides.add();
cover.background.fill = theme.cover;
addText(
  cover,
  String(spec.title || "演示文稿"),
  { left: 88, top: 188, width: 1050, height: 180 },
  { fontSize: 54, bold: true, color: theme.coverText },
);
if (spec.subtitle) {
  addText(
    cover,
    String(spec.subtitle),
    { left: 92, top: 392, width: 920, height: 92 },
    { fontSize: 25, color: theme.coverMuted },
  );
}
addText(
  cover,
  "PRESENTATION",
  { left: 92, top: 110, width: 280, height: 28 },
  { fontSize: 13, bold: true, color: theme.accent },
);

for (const [index, item] of (spec.slides || []).entries()) {
  const slide = presentation.slides.add();
  slide.background.fill = theme.canvas;
  addText(
    slide,
    String(item.title || `第 ${index + 1} 页`),
    { left: 76, top: 58, width: 1040, height: 62 },
    { fontSize: 38, bold: true, color: theme.title },
  );
  addText(
    slide,
    String(index + 2).padStart(2, "0"),
    { left: 1140, top: 64, width: 70, height: 34 },
    { fontSize: 16, bold: true, color: theme.accent, alignment: "right" },
  );

  let top = 154;
  if (item.summary) {
    addText(
      slide,
      String(item.summary),
      { left: 78, top, width: 1060, height: 64 },
      { fontSize: 23, bold: true, color: theme.body },
    );
    top += 86;
  }

  const bullets = Array.isArray(item.bullets) ? item.bullets.slice(0, 7) : [];
  const available = 610 - top;
  const rowHeight = bullets.length > 0
    ? Math.min(72, Math.max(48, Math.floor(available / bullets.length)))
    : 72;
  const fontSize = bullets.length >= 6 ? 20 : 23;
  for (const [bulletIndex, bullet] of bullets.entries()) {
    addText(
      slide,
      `•  ${String(bullet)}`,
      { left: 92, top: top + bulletIndex * rowHeight, width: 1060, height: rowHeight - 6 },
      { fontSize, color: theme.body },
    );
  }
  sourceNotes(slide, item.sources);
}

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(outputPath);
const preview = await presentation.export({
  format: "webp",
  montage: true,
  scale: 0.75,
});
await saveBlob(previewPath, preview);
