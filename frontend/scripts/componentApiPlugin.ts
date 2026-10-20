import ts from "typescript";
import path from "node:path";
import fs from "node:fs";
import type { Plugin } from "vite";

const virtualId = "virtual:component-api";
const resolvedId = "\0" + virtualId;

export function componentApiPlugin(): Plugin {
  let root = "";
  return {
    name: "component-api-docs",
    configResolved(config) { root = config.root; },
    resolveId(id) { if (id === virtualId) return resolvedId; },
    load(id) {
      if (id !== resolvedId) return;
      const directory = path.join(root, "src/components");
      function files(dir: string): string[] {
        return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? files(path.join(dir, entry.name)) : entry.name.endsWith(".tsx") ? [path.join(dir, entry.name)] : []);
      }
      const program = ts.createProgram(files(directory), { jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler, strict: true, skipLibCheck: true, esModuleInterop: true });
      const checker = program.getTypeChecker();
      const docs: Record<string, unknown> = {};
      for (const source of program.getSourceFiles()) {
        if (!source.fileName.startsWith(directory) || !source.fileName.endsWith(".tsx")) continue;
        const module = checker.getSymbolAtLocation(source);
        if (!module) continue;
        for (const symbol of checker.getExportsOfModule(module)) {
          const name = symbol.name;
          if (!/^[A-Z]/.test(name)) continue;
          const declaration = symbol.valueDeclaration;
          if (!declaration) continue;
          const signature = checker.getTypeOfSymbolAtLocation(symbol, declaration).getCallSignatures()[0];
          if (!signature) continue;
          const parameter = signature.parameters[0];
          const defaults: Record<string, string> = {};
          function collect(node: ts.Node) {
            if ((ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node)) && node.parameters[0]) {
              const binding = node.parameters[0].name;
              if (ts.isObjectBindingPattern(binding)) for (const item of binding.elements) {
                if (item.initializer) defaults[(item.propertyName ?? item.name).getText(source).replace(/^['"]|['"]$/g, "")] = item.initializer.getText(source);
              }
              return;
            }
            ts.forEachChild(node, collect);
          }
          collect(declaration);
          const props = parameter ? checker.getPropertiesOfType(checker.getTypeOfSymbolAtLocation(parameter, declaration)).map(prop => {
            const decl = prop.valueDeclaration ?? prop.declarations?.[0] ?? declaration;
            const declarations = prop.declarations ?? [];
            return {
              name: prop.name,
              type: checker.typeToString(checker.getTypeOfSymbolAtLocation(prop, decl), decl, ts.TypeFormatFlags.NoTruncation).replace(/import\("[^"\n]+"\)\./g, ""),
              required: !(prop.flags & ts.SymbolFlags.Optional),
              defaultValue: defaults[prop.name] ?? "未设置",
              description: ts.displayPartsToString(prop.getDocumentationComment(checker)),
              native: declarations.length > 0 && declarations.every(d => !d.getSourceFile().fileName.startsWith(directory)),
            };
          }) : [];
          docs[name] = { name, props };
        }
      }
      return `export default ${JSON.stringify(docs)}`;
    },
    handleHotUpdate(context) {
      if (!context.file.includes("/src/components/") || !/\.tsx?$/.test(context.file)) return;
      const module = context.server.moduleGraph.getModuleById(resolvedId);
      if (module) {
        context.server.moduleGraph.invalidateModule(module);
        context.server.ws.send({ type: "full-reload" });
      }
    },
  };
}
