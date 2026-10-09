import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
const result = await build({stdin:{contents:`export * from './blocks'; export * from './transcriptRows';`,resolveDir:fileURLToPath(new URL('../src',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false});
const api = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString('base64')}`);
const tool='delegate_to_codex_sandbox';
const event=(id,parts,extra={})=>({id,author:'general',invocationId:'one',content:{parts},...extra});
const call=event('call',[{functionCall:{id:'tool',name:tool,args:{}}}]);
const response=event('response',[{functionResponse:{id:'tool',name:tool,response:{ok:true,message:'Result',codex_activity:{events:[{id:'comment',kind:'commentary',text:'Result; additional warning.'},{id:'reason',kind:'reasoning',status:'done',text:'Result requires checking permissions.'}]}}}}]);
const texts=turns=>turns.filter(t=>t.role==='assistant').flatMap(t=>t.blocks).filter(b=>b.kind==='text').map(b=>b.text);
test('general delegate keeps later distinct and streaming text',()=>{
 const turns=api.eventsToTurns([call,response,event('delta',[{text:'Additional'}],{partial:true}),event('final',[{text:'Additional verified detail'}],{partial:false,turnComplete:true})]);
 assert.ok(texts(turns).join('').includes('Additional verified detail'));
});
test('general commentary and reasoning containing the answer retain unique context',()=>{
 const turns=api.eventsToTurns([call,response]);
 const activity=turns.flatMap(t=>t.blocks).find(b=>b.kind==='tool').codexActivity;
 assert.deepEqual(activity.items.map(i=>i.id),['comment','reason']);
});
const user={role:'user',blocks:[{kind:'text',text:'Question'}]};
const final={role:'assistant',blocks:[{kind:'text',text:'Result'}],meta:{localId:'sandbox',eventId:'final',mpaFinalAnswer:'Result',streaming:false}};
const outer=text=>({role:'assistant',blocks:[{kind:'thinking',text:'Additional reasoning',done:true},{kind:'text',text},{kind:'tool',name:'exec',done:true}],meta:{localId:'outer',eventId:'outer-event',streaming:false}});
test('MPA view hides only exact answer mirrors and targets visible answer feedback',()=>{
 const raw=[user,final,outer(' Result ')];const before=JSON.stringify(raw);
 const view=api.groupMpaTranscriptTurns(raw,true,false);
 assert.deepEqual(texts(view),['Result']);assert.equal(view[1].meta.eventId,'final');
 assert.ok(view[1].blocks.some(b=>b.kind==='thinking'));assert.ok(view[1].blocks.some(b=>b.kind==='tool'));
 assert.equal(JSON.stringify(raw),before);assert.equal(api.groupMpaTranscriptTurns(raw,false,false),raw);
});
test('extending a hidden stream mirror restores its full prefix and added detail',()=>{
 const full=outer('Result; additional warning.');
 const view=api.groupMpaTranscriptTurns([user,final,full],true,true);
 assert.deepEqual(texts(view),['Result','Result; additional warning.']);
 assert.equal(view[1].meta.eventId,'outer-event');
 const nextRequest=api.groupMpaTranscriptTurns([user,final,user,outer('Result')],true,false);
 assert.deepEqual(texts(nextRequest),['Result','Result']);
});
test('only MPA A2A marks final ownership in live/history projections',()=>{
 const ev={id:'sandbox-final',author:'outer',invocationId:'sandbox',partial:false,turnComplete:true,customMetadata:{source:'sandbox',eventType:'invocation.completed'},content:{parts:[{text:'Result'}]}};
 for(const mode of [false,true]){
  const p=api.createAssistantEventProjector('live',undefined,{mpaA2a:mode});const live=p.project(ev).turn;
  const history=api.eventsToTurns([ev],{}, {mpaA2a:mode});
  assert.equal(live.meta.mpaFinalAnswer,mode?'Result':undefined);assert.equal(history[0].meta.mpaFinalAnswer,mode?'Result':undefined);
 }
});

test('MPA keeps content-bearing usage and does not erase preview on empty terminal events',()=>{
 const p=api.createAssistantEventProjector('mpa',undefined,{mpaA2a:true});
 p.project({id:'start',author:'outer',partial:true,content:{parts:[{text:'Partial answer'}]}});
 const final=p.project({id:'end',author:'outer',partial:false,turnComplete:true,content:{parts:[]}});
 assert.equal(final.ignored,true);
 assert.equal(texts(p.finish()).join(''),'Partial answer');
 const mixed=p.project({id:'mixed',author:'outer',partial:false,customMetadata:{eventType:'usage.updated'},usageMetadata:{totalTokenCount:5},content:{parts:[{text:'Additional detail'}]}});
 assert.equal(mixed.ignored,undefined);assert.ok(texts([mixed.turn]).join('').includes('Additional detail'));
});

const sandboxEvent = (id, type, parts, extra = {}) => ({
  id, author: 'outer', invocationId: 'worker', partial: type.endsWith('.delta'),
  customMetadata: { source: 'sandbox', eventType: type }, content: { parts }, ...extra,
});
const workerThought = sandboxEvent('worker-thought', 'thought.delta', [{ thought: true, text: 'Worker reasoning' }]);
const answerDelta = sandboxEvent('answer-delta', 'message.delta', [{ text: 'Result' }]);
const workerFinal = sandboxEvent('worker-final', 'invocation.completed', [{ text: 'Result' }], { turnComplete: true });
const thoughts = turns => turns.flatMap(t => t.blocks).filter(b => b.kind === 'thinking').map(b => b.text);
function projectLive(events, options = { mpaA2a: true }) {
  const projector = api.createAssistantEventProjector('replay', undefined, options);
  let turns = [];
  for (const ev of events) {
    const next = projector.project(ev);
    if (!next.ignored) turns = api.upsertProjectedAssistantTurn(turns, next.turn);
  }
  for (const turn of projector.finish()) turns = api.upsertProjectedAssistantTurn(turns, turn);
  return turns;
}
test('MPA sandbox final preserves both reasoning stages in live and full-event replay', () => {
  const events = [event('outer-thought', [{ thought: true, text: 'Outer reasoning' }], { partial: false }), workerThought, answerDelta, workerFinal, workerFinal];
  for (const turns of [projectLive(events), api.eventsToTurns(events, {}, { mpaA2a: true })]) {
    const view = api.groupMpaTranscriptTurns(turns, true, false);
    assert.deepEqual(thoughts(view), ['Outer reasoning', 'Worker reasoning']);
    assert.deepEqual(texts(view), ['Result']);
    assert.ok(view.flatMap(t => t.blocks).filter(b => b.kind === 'thinking').every(b => b.done));
  }
});
test('MPA sandbox tool and failure events preserve preceding reasoning', () => {
  const call = sandboxEvent('worker-call', 'tool.call', [{ functionCall: { id: 'inspect', name: 'inspect', args: {} } }]);
  const response = sandboxEvent('worker-result', 'tool.result', [{ functionResponse: { id: 'inspect', name: 'inspect', response: { ok: true } } }]);
  const turns = projectLive([workerThought, call, response, answerDelta, workerFinal]);
  assert.deepEqual(thoughts(turns), ['Worker reasoning']);
  assert.equal(turns.flatMap(t => t.blocks).filter(b => b.kind === 'tool').length, 1);
  const failed = sandboxEvent('worker-failure', 'invocation.failed', [{ text: 'Execution failed' }], { turnComplete: true });
  const failedTurns = projectLive([workerThought, failed]);
  assert.deepEqual(thoughts(failedTurns), ['Worker reasoning']);
  assert.deepEqual(texts(failedTurns), ['Execution failed']);
});
test('MPA sandbox authoritative thought snapshot replaces preview; interrupted preview remains', () => {
  const snapshot = sandboxEvent('snapshot', 'snapshot', [{ thought: true, text: 'Worker reasoning complete' }]);
  assert.deepEqual(thoughts(projectLive([workerThought, snapshot, answerDelta, workerFinal])), ['Worker reasoning complete']);
  const stopped = projectLive([workerThought, answerDelta]);
  assert.deepEqual(thoughts(stopped), ['Worker reasoning']);
  assert.deepEqual(texts(stopped), ['Result']);
});
test('sandbox reasoning preservation is scoped to MPA mode and invocation', () => {
  const other = { ...workerThought, id: 'other', invocationId: 'other-worker', content: { parts: [{ thought: true, text: 'Other worker' }] } };
  const turns = projectLive([workerThought, other, answerDelta, workerFinal]);
  assert.deepEqual(thoughts(turns), ['Worker reasoning', 'Other worker']);
  for (const options of [{}, { mpaA2a: false }]) {
    assert.deepEqual(thoughts(projectLive([workerThought, answerDelta, workerFinal], options)), []);
  }
});

test('MPA delayed reasoning tail stays before its tool while later segments remain distinct', () => {
 const segment = (id, text, segmentId) => sandboxEvent(id, 'thought.delta', [{ thought: true, text }], {customMetadata:{source:'sandbox',eventType:'thought.delta',reasoningSegmentId:segmentId}});
 const call = sandboxEvent('late-call','tool.call',[{functionCall:{id:'tool',name:'inspect',args:{}}}]);
 const result = sandboxEvent('late-result','tool.result',[{functionResponse:{id:'tool',name:'inspect',response:{ok:true}}}]);
 const events=[segment('a','Read skill','first'),call,segment('b','.','first'),result,segment('c','New conclusion','next'),workerFinal];
 for(const turns of [projectLive(events),api.eventsToTurns(events,{}, {mpaA2a:true})]){
  assert.deepEqual(thoughts(turns),['Read skill.','New conclusion']);
  assert.deepEqual(turns.flatMap(t=>t.blocks).map(b=>b.kind),['thinking','tool','thinking','text']);
 }
 const general=projectLive([segment('d','Read skill','first'),call,segment('e','.','first')],{mpaA2a:false});
 assert.deepEqual(thoughts(general),['.']);
});

const directThought = event('direct-thought', [{ thought: true, text: 'Direct reasoning' }], {
 partial: true, customMetadata: { projectionSource: 'a2a-status', reasoningSegmentId: 'outer-phase' },
});
const directDelta = event('direct-delta', [{ text: 'Preview answer' }], { partial: true });
const directFinal = event('direct-final', [{ text: 'Corrected answer' }], { partial: false, turnComplete: true });
test('MPA direct final retains completed reasoning and replaces only the answer preview', () => {
 const events = [directThought, directDelta, directFinal];
 for (const raw of [projectLive(events), api.eventsToTurns(events, {}, { mpaA2a: true })]) {
  const turns = api.groupMpaTranscriptTurns(raw, true, false);
  assert.deepEqual(thoughts(turns), ['Direct reasoning']);
  assert.deepEqual(texts(turns), ['Corrected answer']);
  assert.ok(turns.flatMap(t => t.blocks).filter(b => b.kind === 'thinking').every(b => b.done));
  assert.equal(turns[0].meta.streaming, false);
 }
 for (const options of [{}, { mpaA2a: false }]) {
  assert.deepEqual(thoughts(projectLive(events, options)), []);
  assert.deepEqual(texts(projectLive(events, options)), ['Corrected answer']);
 }
});
test('MPA outer reasoning survives tools and interruption but authoritative thought replaces preview', () => {
 const toolCall = event('direct-call', [{ functionCall: { id: 'lookup', name: 'lookup', args: {} } }]);
 const turns = projectLive([directThought, toolCall, directFinal]);
 assert.deepEqual(thoughts(turns), ['Direct reasoning']);
 assert.equal(turns.flatMap(t => t.blocks).filter(b => b.kind === 'tool').length, 1);
 const snapshot = event('direct-snapshot', [{ thought: true, text: 'Authoritative reasoning' }], { partial: false });
 assert.deepEqual(thoughts(projectLive([directThought, snapshot, directFinal])), ['Authoritative reasoning']);
 const stopped = projectLive([directThought, directDelta]);
 assert.deepEqual(thoughts(stopped), ['Direct reasoning']);
 assert.deepEqual(texts(stopped), ['Preview answer']);
});
