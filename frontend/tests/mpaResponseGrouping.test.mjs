import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
const result = await build({stdin:{contents:`export * from './transcriptRows'; export * from './blocks';`,resolveDir:fileURLToPath(new URL('../src',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false});
const api = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString('base64')}`);
const user = {role:'user',blocks:[{kind:'text',text:'Question'}]};
const outer = {role:'assistant',blocks:[{kind:'thinking',text:'Plan',done:true}],meta:{localId:'outer',eventId:'plan',invocationId:'outer',ts:10,streaming:false}};
const answer = {role:'assistant',blocks:[{kind:'text',text:'Answer'}],meta:{localId:'worker',eventId:'answer',invocationId:'worker',ts:20,streaming:false}};
const group = (turns,busy=false)=>api.groupMpaTranscriptTurns(turns,true,busy);

test('MPA response groups without mutating source; feedback targets answer, trace includes latest phase',()=>{
 const turns=[user,outer,answer,{...outer,meta:{...outer.meta,localId:'late',ts:30}}];
 const before=JSON.stringify(turns);const view=group(turns);
 assert.equal(view.length,2);assert.equal(view[1].meta.localId,'outer');assert.equal(view[1].meta.eventId,'answer');assert.equal(view[1].meta.ts,30);
 assert.deepEqual(view[1].blocks.map(b=>b.kind),['thinking','text','thinking']);assert.equal(JSON.stringify(turns),before);
});
test('general transcript identity and user/system boundaries are preserved',()=>{
 const system={role:'system',blocks:[],activity:{id:'activity',title:'Activity'}};
 const turns=[user,outer,answer,user,outer,system,answer];
 assert.equal(api.groupMpaTranscriptTurns(turns,false,true),turns);
 assert.deepEqual(group(turns).map(t=>t.role),['user','assistant','user','assistant','system','assistant']);
});
test('streaming group retains stable identity and only current request gets busy override',()=>{
 assert.equal(group([user,outer],true)[1].meta.localId,group([user,outer,answer],true)[1].meta.localId);
 const view=group([user,outer,user,answer],true);assert.equal(view[1].meta.streaming,false);assert.equal(view[3].meta.streaming,true);
 assert.equal(group([user,outer,answer])[1].meta.streaming,false);
});
test('tools, auth, attachments and partial content survive completion or cancellation',()=>{
 const tools={role:'assistant',blocks:[{kind:'tool',name:'execute',done:true,status:'failed'},{kind:'auth',done:false},{kind:'attachment',files:[]}]};
 assert.deepEqual(group([user,outer,tools,answer])[1].blocks,[...outer.blocks,...tools.blocks,...answer.blocks]);
});
test('request ledgers deduplicate snapshots while retaining independent equal-count calls',()=>{
 const first={...outer,meta:{...outer.meta,mpaUsage:{a:10,b:10}}};
 const last={...answer,meta:{...answer.meta,mpaUsage:{a:10,b:10,c:4}}};
 assert.equal(group([user,first,last])[1].meta.tokens,24);
 assert.equal(group([user,{...outer,meta:{...outer.meta,tokens:10}}, {...outer,meta:{...outer.meta,tokens:15}}, {...answer,meta:{...answer.meta,tokens:20}}])[1].meta.tokens,35);
});
const usage=(id,count,source='sandbox')=>({id,author:'outer',partial:true,customMetadata:{source,eventType:'usage.updated',requestId:'call'},usageMetadata:{totalTokenCount:count},content:{parts:[]}});
const thought={id:'thought',author:'outer',partial:false,content:{parts:[{thought:true,text:'Plan'}]}};
const final={id:'final',author:'outer',invocationId:'worker',partial:false,turnComplete:true,customMetadata:{source:'sandbox',eventType:'invocation.completed'},content:{parts:[{text:'Answer'}]}};
test('MPA live/history include early and trailing usage exactly once without extra empty turns',()=>{
 const events=[usage('early',5,'outer'),thought,usage('worker1',7),usage('worker1',7),final,usage('worker2',3)];
 const p=api.createAssistantEventProjector('test',undefined,{mpaA2a:true});let turns=[user];
 for(const ev of events){const projection=p.project(ev);if(!projection.ignored)turns=api.upsertProjectedAssistantTurn(turns,projection.turn);}
 for(const t of p.finish())turns=api.upsertProjectedAssistantTurn(turns,t);
 const view=group(turns);assert.equal(view.length,2);assert.equal(view[1].meta.tokens,15);assert.equal(view[1].meta.eventId,'final');
 const history=api.eventsToTurns([{author:'user',content:{parts:[{text:'Question'}]}},...events],{},{mpaA2a:true});
 assert.equal(group(history)[1].meta.tokens,15);
 const general=api.eventsToTurns(events);assert.ok(general.every(t=>!t.meta?.mpaUsage));
});
test('source identity distinguishes equal usage IDs and resets on next request',()=>{
 const events=[thought,usage('same',5,'outer'),usage('same',5,'sandbox'),final];
 const turns=api.eventsToTurns(events,{}, {mpaA2a:true});assert.equal(group(turns)[0].meta.tokens,10);
 const history=api.eventsToTurns([...events,{author:'user',content:{parts:[{text:'Next'}]}},...events],{}, {mpaA2a:true});
 assert.deepEqual(group(history).filter(t=>t.role==='assistant').map(t=>t.meta.tokens),[10,10]);
});

test('auth continuation preserves the prior usage ledger and unlabelled replay is conservative',()=>{
 const first=usage(undefined,5);const p=api.createAssistantEventProjector('first',undefined,{mpaA2a:true});
 let turn=p.project(thought).turn;turn=p.project(first).turn;
 const resumed=api.createAssistantEventProjector('resume',turn,{mpaA2a:true});
 assert.equal(resumed.project(first).ignored,true);
 const finalTurn=resumed.project(final).turn;
 assert.equal(group([finalTurn])[0].meta.tokens,5);
});

test('presentation and annotations share the scoped view while stream state stays raw',async()=>{
 const {readFileSync}=await import('node:fs');
 const source=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
 assert.match(source,/groupMpaTranscriptTurns\(\s*turns,\s*isMpaA2aRuntimeApp\(appName\)/);
 assert.match(source,/buildTranscriptRows\(transcriptTurns, rootCapabilityNode\)/);
 assert.match(source,/transcriptTurns\.forEach\(\(turn, index\)/);
 assert.match(source,/const turn = transcriptTurns\[i\]/);
 assert.match(source,/upsertProjectedAssistantTurn\(turns, projection.turn\)/);
});
