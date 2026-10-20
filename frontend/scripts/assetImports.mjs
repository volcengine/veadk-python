import ts from "typescript";

/** Read literal module references without matching examples in strings or comments. */
export function extractJavaScriptImports(contents, fileName = "asset.js") {
  const source = ts.createSourceFile(
    fileName,
    contents,
    ts.ScriptTarget.Latest,
    false,
    ts.ScriptKind.JS,
  );
  const references = [];
  function visit(node) {
    const specifier = ts.isImportDeclaration(node) || ts.isExportDeclaration(node)
      ? node.moduleSpecifier
      : ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword
        ? node.arguments[0]
        : undefined;
    if (specifier && ts.isStringLiteralLike(specifier)) references.push(specifier.text);
    ts.forEachChild(node, visit);
  }
  visit(source);
  return references;
}
