import assert from "node:assert/strict";
import test from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
import ts from "typescript";
const buildResult = await build({
  stdin: { contents: `export * from './blocks';`, resolveDir: fileURLToPath(new URL('../src', import.meta.url)), loader: 'ts' },
  bundle: true, platform: 'node', format: 'esm', write: false,
});
const api = await import(`data:text/javascript;base64,${Buffer.from(buildResult.outputFiles[0].contents).toString('base64')}`);
const opts = { mpaA2a: true };
const thought = (id, text, extra = {}) => ({
  id, author: 'outer', partial: false,
  content: { role: 'model', parts: [{ thought: true, text }] },
  customMetadata: { projectionSource: 'a2a-artifact', thoughtKind: 'reasoning' },
  ...extra,
});
const final = { id: 'final', author: 'outer', invocationId: 'worker', partial: false, turnComplete: true, customMetadata: {source:'sandbox',eventType:'invocation.completed'}, content: {parts:[{text:'Answer'}]} };
const reasoning = turns => turns.flatMap(t=>t.blocks).filter(b=>b.kind==='thinking').map(b=>b.text).join('');
const hasVisible = turn => turn.blocks.some(b=>b.kind==='text'&&b.text.trim() || b.kind==='tool' || b.kind==='attachment');
const user = {role:'user',blocks:[{kind:'text',text:'Question'}]};
const reasoningTurn = {role:'assistant',blocks:[{kind:'thinking',text:'Planning',done:true}]};
const answerTurn = {role:'assistant',blocks:[{kind:'text',text:'Answer'}]};
const note = (turns,index,extra={}) => api.shouldShowEmptyAssistantResponse(turns,index,hasVisible,{mpaA2a:true,turnIsStreaming:false,requestIsStreaming:false,...extra});

test('MPA A2A live and history consolidate repeated/extended outer snapshots',()=>{
  const events=[thought('snapshot','Plan'),thought('snapshot-replay','Plan'),thought('snapshot-more','Plan then act'),final];
  const projector=api.createAssistantEventProjector('live',undefined,opts);
  let turns=[];
  for(const ev of events){const p=projector.project(ev);if(!p.ignored)turns=api.upsertProjectedAssistantTurn(turns,p.turn)}
  for(const t of projector.finish())turns=api.upsertProjectedAssistantTurn(turns,t);
  assert.equal(reasoning(turns),'Plan then act');
  assert.equal(reasoning(api.eventsToTurns(events,{},opts)),'Plan then act');
  assert.equal(turns.flatMap(t=>t.blocks).filter(b=>b.kind==='text').length,1);
});

test('general ADK/A2A default projection is unchanged for the same events',()=>{
  const events=[thought('one','Plan'),thought('two','Plan'),final];
  assert.equal(reasoning(api.eventsToTurns(events)),'PlanPlan');
  assert.equal(reasoning(api.eventsToTurns(events,{}, {mpaA2a:false})),'PlanPlan');
});

test('MPA A2A preserves distinct reasoning, repeated deltas, sandbox thoughts and tools',()=>{
  assert.equal(reasoning(api.eventsToTurns([thought('one','First'),thought('two','Different')],{},opts)),'FirstDifferent');
  assert.equal(reasoning(api.eventsToTurns([thought('one','go ',{partial:true}),thought('two','go ',{partial:true})],{},opts)),'go go ');
  const sandbox={customMetadata:{source:'sandbox',eventType:'thought.delta'},invocationId:'worker'};
  assert.equal(reasoning(api.eventsToTurns([thought('one','Plan',sandbox),thought('two','Plan',sandbox)],{},opts)),'PlanPlan');
  const tool={id:'tool',author:'outer',partial:false,content:{parts:[{functionCall:{id:'tool-1',name:'inspect',args:{}}}]}};
  const turns=api.eventsToTurns([thought('one','Plan'),tool,thought('two','Plan')],{},opts);
  assert.equal(reasoning(turns),'PlanPlan');
  assert.equal(turns.flatMap(t=>t.blocks).filter(b=>b.kind==='tool').length,1);
});

test('snapshot reconciliation does not cross requests or parallel invocation identities',()=>{
  const u={author:'user',content:{parts:[{text:'Again'}]}};
  assert.equal(reasoning(api.eventsToTurns([thought('one','Plan'),u,thought('two','Plan')],{},opts)),'PlanPlan');
  assert.equal(reasoning(api.eventsToTurns([thought('one','Plan',{invocationId:'a'}),thought('two','Plan',{invocationId:'b'})],{},opts)),'PlanPlan');
});

test('MPA A2A reasoning fragment never reports empty while the request is running',()=>{
  assert.equal(note([user,reasoningTurn],1,{requestIsStreaming:true}),false);
  assert.equal(note([user,reasoningTurn],1,{turnIsStreaming:true}),false);
});

test('MPA A2A visible answer, tool or attachment prevents misleading empty notices',()=>{
  for(const visible of [answerTurn,{role:'assistant',blocks:[{kind:'tool',name:'exec'}]},{role:'assistant',blocks:[{kind:'attachment',files:[{}]}]}]){
    assert.equal(note([user,reasoningTurn,visible],1),false);
    assert.equal(note([user,visible,reasoningTurn],2),false);
  }
});

test('genuinely empty completed or stopped request retains exactly one notice',()=>{
  const turns=[user,reasoningTurn,reasoningTurn,{role:'assistant',blocks:[]}];
  assert.equal(note(turns,1),false);
  assert.equal(note(turns,2),true);
});

test('empty notice does not use another user request to hide missing content',()=>{
  const turns=[user,reasoningTurn,user,answerTurn];
  assert.equal(note(turns,1),true);
  assert.equal(note([user,reasoningTurn,user,reasoningTurn],1,{requestIsStreaming:true}),true);
});

test('general agents retain the old per-turn empty response rule',()=>{
  assert.equal(note([user,reasoningTurn,answerTurn],1,{mpaA2a:false}),true);
  assert.equal(note([user,reasoningTurn],1,{mpaA2a:false,requestIsStreaming:true}),true);
  assert.equal(note([user,reasoningTurn],1,{mpaA2a:false,turnIsStreaming:true}),false);
});

test('all App stream and history entry points pass an explicit MPA A2A gate',()=>{
  const source=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  const ast=ts.createSourceFile('App.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  let calls=0;
  function visit(node){
    if(ts.isCallExpression(node)&&['createAssistantEventProjector','eventsToTurns'].includes(node.expression.getText(ast))){
      calls++;
      assert.equal(node.arguments.length,3);
      assert.match(node.arguments[2].getText(ast),/mpaA2a: isMpaA2aRuntimeApp\((app|appName)\)/);
    }
    ts.forEachChild(node,visit);
  }
  visit(ast);
  assert.equal(calls,5);
  assert.match(source,/shouldShowEmptyAssistantResponse\(transcriptTurns, i, turnHasVisibleContent, \{\s*mpaA2a: isMpaA2aRuntimeApp\(appName\)/);
});
