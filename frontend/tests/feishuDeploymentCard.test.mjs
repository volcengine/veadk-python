import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const componentSource = readFileSync(
  new URL("../src/ui/FeishuDeploymentCard.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/ui/FeishuDeploymentCard.css", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);

test("keeps Feishu setup as a standalone deployment channel card", () => {
  assert.match(componentSource, /export function FeishuDeploymentCard/);
  assert.match(componentSource, /role="tablist" aria-label="飞书配置方式"/);
  assert.match(componentSource, />\s*自动配置\s*<\/button>/);
  assert.doesNotMatch(componentSource, /推荐/);
  assert.match(componentSource, />\s*手动配置\s*<\/button>/);
  assert.match(componentSource, /onCredentialsChange/);
  assert.match(
    stylesSource,
    /\.fdc-card\.is-open \.fdc-card-inner\s*\{[\s\S]*?transform:\s*rotateY\(180deg\);/,
  );
  assert.match(stylesSource, /\.fdc-card\s*\{[\s\S]*?height:\s*112px;/);
  assert.doesNotMatch(
    stylesSource,
    /\.fdc-card\.is-open\s*\{[^}]*\b(?:width|height)\s*:/,
  );
  assert.doesNotMatch(componentSource, /is-manual|is-auto-success/);
  assert.match(componentSource, /tabIndex=\{enabled \? 0 : -1\}/);
  assert.match(
    componentSource,
    /appIdConfigured \? "已配置，留空沿用" : "cli_xxxxxxxxxxxxxxxx"/,
  );
  assert.match(
    componentSource,
    /appSecretConfigured \? "已配置，留空沿用" : "请输入 App Secret"/,
  );
  assert.doesNotMatch(componentSource, /from "lucide-react"/);
});

test("renders the card in the real final deployment step", () => {
  assert.match(
    projectPreviewSource,
    /<div className="pp-config-label">消息渠道<\/div>/,
  );
  assert.match(projectPreviewSource, /<FeishuDeploymentCard/);
  assert.match(
    projectPreviewSource,
    /onFeishuCredentialsChange\?\.\(appId, appSecret\)/,
  );
  assert.doesNotMatch(
    projectPreviewSource,
    /onDeploymentEnvChange\?\.\("FEISHU_APP_(?:ID|SECRET)",/,
  );
  assert.doesNotMatch(projectPreviewSource, /创建机器人 Runtime/);
});
