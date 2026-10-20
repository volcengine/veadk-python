const initializedKey = 'studio.terminalsInitialized';

function openTerminals(vscode) {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder || folder.uri.scheme !== 'file') return false;
  const cwd = folder.uri.fsPath;
  const definitions = [
    {name: 'Bash', shellPath: '/bin/bash', shellArgs: []},
    {name: 'Codex', shellPath: '/usr/local/bin/codex', shellArgs: ['--cd', cwd]}
  ];
  for (const definition of definitions) {
    if (!vscode.window.terminals.some(terminal => terminal.name === definition.name)) {
      const terminal = vscode.window.createTerminal({...definition, cwd});
      if (definition.name === 'Bash') terminal.show(true);
    }
  }
  return true;
}

async function initializeTerminals(vscode, state) {
  // Restored terminals can arrive after activation. A persisted first-open marker
  // prevents a reload from racing restoration or reopening terminals the user closed.
  if (state.get(initializedKey, false)) return;
  if (openTerminals(vscode)) await state.update(initializedKey, true);
}

module.exports = {initializeTerminals, openTerminals};
