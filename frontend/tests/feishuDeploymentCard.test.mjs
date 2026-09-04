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
  assert.match(componentSource, /role="tablist" aria-label=\{t\("feishuDeployment\.configurationMode"\)\}/);
  assert.match(componentSource, /t\("feishuDeployment\.automatic"\)/);
  assert.match(componentSource, /t\("feishuDeployment\.manual"\)/);
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
    /appIdConfigured \? t\("feishuDeployment\.configuredPlaceholder"\) : "cli_xxxxxxxxxxxxxxxx"/,
  );
  assert.match(
    componentSource,
    /appSecretConfigured \? t\("feishuDeployment\.configuredPlaceholder"\) : t\("feishuDeployment\.appSecretPlaceholder"\)/,
  );
  assert.doesNotMatch(componentSource, /from "lucide-react"/);
});

test("renders the card in the real final deployment step", () => {
  assert.match(
    projectPreviewSource,
    /<div className="pp-config-label">\{t\("projectPreview\.messageChannels"\)\}<\/div>/,
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
