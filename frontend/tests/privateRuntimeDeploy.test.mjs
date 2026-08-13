import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const configYamlSource = readFileSync(
  new URL("../src/create/configYaml.ts", import.meta.url),
  "utf8",
);

test("AgentKit deploy accepts private runtimes that only return runtimeId", () => {
  assert.doesNotMatch(clientSource, /!final\.url\s*\|\|\s*!final\.agentName/);
  assert.match(clientSource, /if \(!final\.agentName\)/);
  assert.match(clientSource, /if \(!final\.runtimeId && !final\.url\)/);
  assert.match(clientSource, /url:\s*final\.url \?\? ""/);
});

test("deployment identity keeps ADK agent and platform Runtime names distinct", () => {
  assert.match(
    clientSource,
    /interface DeployAgentkitResult[\s\S]*agentName: string;[\s\S]*runtimeName: string;/,
  );
  assert.match(
    clientSource,
    /const deployedAgentName = final\.runtimeName\?\.trim\(\) \? final\.agentName : name;/,
  );
  assert.match(
    clientSource,
    /const deployedRuntimeName = final\.runtimeName\?\.trim\(\) \|\| final\.agentName;/,
  );
  assert.match(clientSource, /agentName: deployedAgentName/);
  assert.match(clientSource, /runtimeName: deployedRuntimeName/);
  assert.match(
    projectPreviewSource,
    /runtimeName: result\.runtimeName \|\| taskRuntimeName/,
  );
  assert.match(projectPreviewSource, /<label>Runtime 名称<\/label>/);
});

test("new deployments use an explicit persisted Runtime name without a random suffix", () => {
  assert.match(clientSource, /runtimeName: opts\?\.runtimeName/);
  assert.match(projectPreviewSource, /aria-label="Runtime 名称"/);
  assert.match(
    projectPreviewSource,
    /const requestedRuntimeName = effectiveRuntimeName\.trim\(\)/,
  );
  assert.match(projectPreviewSource, /runtimeName: requestedRuntimeName/);
  assert.match(customCreateSource, /resolveRuntimeName\([\s\S]*?draft\.name/);
  assert.match(customCreateSource, /onDeploymentRuntimeNameChange=/);
  assert.match(customCreateSource, /runtimeNameCustomized: true/);
  assert.match(configYamlSource, /deployment\.runtimeName = draft\.deployment\.runtimeName\.trim\(\)/);
  assert.match(configYamlSource, /deployment\.runtimeNameCustomized = true/);
});
