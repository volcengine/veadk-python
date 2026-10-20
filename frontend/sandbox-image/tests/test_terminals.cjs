const {test} = require('node:test');
const assert = require('node:assert/strict');
const {initializeTerminals} = require('../runtime/studio-welcome/terminals');

function fixture(state = new Map(), terminals = []) {
  const created = [];
  return {
    created,
    state: {get: (key, fallback) => state.get(key) ?? fallback, update: async (key, value) => state.set(key, value)},
    vscode: {
      workspace: {workspaceFolders: [{uri: {scheme: 'file', fsPath: '/home/gem/Projects/demo'}}]},
      window: {terminals, createTerminal: options => {
        created.push(options);
        terminals.push(options);
        return {show() {}};
      }}
    }
  };
}

test('first open creates Bash and Codex in the project', async () => {
  const f = fixture();
  await initializeTerminals(f.vscode, f.state);
  assert.deepEqual(f.created.map(t => t.name), ['Bash', 'Codex']);
  assert.ok(f.created.every(t => t.cwd === '/home/gem/Projects/demo'));
  assert.deepEqual(f.created[1].shellArgs, ['--cd', '/home/gem/Projects/demo']);
});

test('reload before terminal restoration does not create another pair', async () => {
  const state = new Map();
  const first = fixture(state);
  await initializeTerminals(first.vscode, first.state);
  const reload = fixture(state);
  await initializeTerminals(reload.vscode, reload.state);
  assert.equal(reload.created.length, 0);
  reload.vscode.window.terminals.push(...first.created);
  assert.equal(reload.vscode.window.terminals.length, 2);
});

test('first activation reuses existing terminals and does not close user terminals', async () => {
  const terminals = [{name: 'Bash'}, {name: 'my server'}];
  const f = fixture(new Map(), terminals);
  await initializeTerminals(f.vscode, f.state);
  assert.deepEqual(f.created.map(t => t.name), ['Codex']);
  assert.equal(terminals[1].name, 'my server');
});

test('empty window does not mark a project initialized', async () => {
  const f = fixture();
  f.vscode.workspace.workspaceFolders = [];
  await initializeTerminals(f.vscode, f.state);
  assert.equal(f.created.length, 0);
  assert.equal(f.state.get('studio.terminalsInitialized', false), false);
});
