import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { JSDOM } from "jsdom";
import ts from "typescript";

const source = ts.createSourceFile(
  "App.tsx",
  readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8"),
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
);

function findNode(predicate, node = source) {
  return predicate(node) ? node : ts.forEachChild(node, (child) => findNode(predicate, child));
}

function bindCallback(node, bindings) {
  assert.ok(node, "App navigation callback must exist");
  const { outputText } = ts.transpileModule(`return (${node.getText(source)});`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  });
  return Function(...Object.keys(bindings), outputText)(...Object.values(bindings));
}

const deploymentSetter = findNode((node) =>
  ts.isVariableDeclaration(node) && node.name.getText(source) === "setIntelligentDeployment",
).initializer.arguments[0];
const intelligentCard = findNode((node) => ts.isObjectLiteralExpression(node)
  && node.properties.some((property) => ts.isPropertyAssignment(property)
    && property.name.getText(source) === "key"
    && ts.isStringLiteral(property.initializer)
    && property.initializer.text === "intelligent"));
const enterIntelligentCreate = intelligentCard.properties.find((property) =>
  ts.isPropertyAssignment(property) && property.name.getText(source) === "onClick",
).initializer;

test("entering intelligent build clears the previous deployment and its reload URL", () => {
  const dom = new JSDOM("", { url: "https://studio.example.test/?unrelated=keep#workspace" });
  const state = { createView: null, addMenu: true, intelligentDeployment: null };
  const setIntelligentDeployment = bindCallback(deploymentSetter, {
    window: dom.window,
    setIntelligentDeploymentState: (value) => { state.intelligentDeployment = value; },
  });
  const enterHome = bindCallback(enterIntelligentCreate, {
    setIntelligentDeployment,
    ...Object.fromEntries([
      "AddMenu", "ImportedDraft", "RuntimeUpdateTarget", "FocusedDeploymentTaskId",
      "FocusedWorkspaceAgentId", "EditingDraftId", "MigrationProjectReturn", "CreateView",
    ].map((name) => [`set${name}`, (value) => {
      state[name[0].toLowerCase() + name.slice(1)] = value;
    }])),
    editingDraftBaselineRef: { current: null },
  });

  try {
    // Both current-session and saved-project deliveries share this navigation.
    for (const project of [{}, { projectId: "project-1", versionId: "version-1" }]) {
      const delivery = {
        sessionId: "build-session",
        artifactSha256: "a".repeat(64),
        validationReportSha256: "b".repeat(64),
        ...project,
      };
      setIntelligentDeployment(delivery);
      assert.equal(state.intelligentDeployment, delivery);
      assert.equal(new URL(dom.window.location.href).searchParams.get("view"), "runtime-deploy");

      enterHome();

      assert.equal(state.createView, "intelligent");
      assert.equal(state.addMenu, false);
      assert.equal(state.intelligentDeployment, null, "A previous deployment must not cover the home page");
      assert.equal(dom.window.location.search, "?unrelated=keep", "Reload must not restore the previous deployment");
      assert.equal(dom.window.location.hash, "#workspace");

      enterHome();
      assert.equal(state.intelligentDeployment, null, "Repeated entry remains on the home page");
    }
  } finally {
    dom.window.close();
  }
});
