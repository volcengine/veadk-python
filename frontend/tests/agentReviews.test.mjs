import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
const require = createRequire(import.meta.url);
const React = require('react');
const { act } = React;
const resources = JSON.parse(readFileSync(new URL('../src/i18n/resources/zh-CN/agentReviews.json', import.meta.url), 'utf8'));
const result = await build({
  entryPoints: [fileURLToPath(new URL('../src/agent-reviews/AgentReviewDialog.tsx', import.meta.url))],
  bundle: true, format: 'cjs', platform: 'node', write: false,
  external: ['react', 'react-dom', 'react-dom/*'],
  plugins: [{name:'review-test-adapters', setup(builder) {
    builder.onResolve({filter:/^react-i18next$/},()=>({path:'i18n',namespace:'mock'}));
    builder.onResolve({filter:/\/adk\/agentReviews$/},()=>({path:'api',namespace:'mock'}));
    builder.onResolve({filter:/\/ui\/ResourceCollection$/},()=>({path:'resources',namespace:'mock'}));
    builder.onResolve({filter:/^@base-ui\/react\/dialog$/},()=>({path:'dialog',namespace:'mock'}));
    builder.onLoad({filter:/.*/,namespace:'mock'},(args)=>({contents: {
      i18n: `const resources=${JSON.stringify(resources)}; export function useTranslation(){return {i18n:{language:'zh-CN'},t(key){return key.split('.').reduce((o,k)=>o?.[k],resources)||key}}}`,
      api: `export const readAgentReview=(...args)=>globalThis.reviewApi.read(...args);export const changeAgentReview=(...args)=>globalThis.reviewApi.change(...args);`,
      resources: `import React from 'react';export function ResourceLoadingState(){return React.createElement('div',{role:'status'},'Loading')}`,
      dialog: `import React from 'react';const wrap=(tag,extra={})=>({children,...props})=>React.createElement(tag,{...extra,disabled:props.disabled,'aria-label':props['aria-label']},children);export const Dialog={Root:wrap('div'),Portal:wrap('div'),Backdrop:wrap('div'),Popup:wrap('section',{role:'dialog'}),Title:wrap('h2'),Description:wrap('p'),Close:wrap('button')};`,
    }[args.path]}));
    builder.onLoad({filter:/\.css$/},()=>({contents:'',loader:'js'}));
  }}],
});
const module={exports:{}};
Function('require','module','exports',result.outputFiles[0].text)(require,module,module.exports);
const {AgentReviewDialog}=module.exports;
const applicant={id:'developer',name:'开发者',email:'',avatarUrl:''};
const admin={id:'admin',name:'审核员',email:'admin@example.com',avatarUrl:'https://example.com/avatar.png'};
const pending={id:'request-1',runtimeId:'runtime-1',region:'cn-beijing',status:'pending',snapshot:{name:'示例智能体',description:'整理工作记录',version:1,model:'demo-model',environmentKeys:[]},submitter:applicant,submittedAt:'2026-09-11T10:00:00Z',message:'请审核',reviewer:null,reviewedAt:'',comment:'',reason:'',published:false};
async function mount(api,canPublish=false){
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost',pretendToBeVisual:true});
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,HTMLElement:dom.window.HTMLElement,Node:dom.window.Node,IS_REACT_ACT_ENVIRONMENT:true,reviewApi:api};
 const previous=new Map(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true,writable:true});
 const root=require('react-dom/client').createRoot(document.getElementById('root'));
 let changes=0;
 await act(async()=>root.render(React.createElement(AgentReviewDialog,{runtimeId:'runtime-1',region:'cn-beijing',name:'示例智能体',canPublish,onClose(){},onChanged(){changes++}})));
 return {get changes(){return changes},async close(){await act(async()=>root.unmount());dom.window.close();for(const[k,d]of previous){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}}};
}
const button=(label)=>[...document.querySelectorAll('button')].find(b=>b.textContent===label);
test('developer can submit and pending requests cannot be directly published',async()=>{
 const writes=[]; const view=await mount({read:async()=>({application:null}),change:async(...args)=>{writes.push(args);return pending}});
 try{assert.ok(button('申请公开'));assert.equal(button('直接公开'),undefined);await act(async()=>button('申请公开').click());assert.equal(writes[0][1],'submit');assert.match(document.body.textContent,/待审核/);assert.equal(button('申请公开'),undefined);assert.ok(button('撤回申请'));assert.equal(view.changes,1)}finally{await view.close()}
});
test('admin approval uses the displayed application id and shows its saved reviewer',async()=>{
 const writes=[];const view=await mount({read:async()=>({application:pending}),change:async(...args)=>{writes.push(args);return {...pending,status:'approved',published:true,reviewer:admin,reviewedAt:'2026-09-11T11:00:00Z',comment:'已验证'}}},true);
 try{await act(async()=>button('通过').click());assert.equal(writes[0][2].applicationId,'request-1');assert.equal(writes[0][2].decision,'approved');assert.match(document.body.textContent,/审核员/);assert.match(document.body.textContent,/已验证/);assert.equal(document.querySelector('img').getAttribute('src'),admin.avatarUrl);assert.ok(button('取消公开'))}finally{await view.close()}
});
test('return requires a reason and altered submissions cannot be approved',async()=>{
 const view=await mount({read:async()=>({application:{...pending,contentChanged:true}})},true);
 try{assert.equal(button('通过').disabled,true);await act(async()=>button('退回').click());assert.equal(button('退回').disabled,true);assert.ok(document.querySelector('textarea[required]'));assert.match(document.body.textContent,/提交后内容已变化/)}finally{await view.close()}
});
test('cloud errors retain the original request id and reload is available',async()=>{
 let attempt=0;const error='{"ResponseMetadata":{"RequestId":"original-log-id","Error":{"Code":"AccessDenied"}}}';
 const view=await mount({read:async()=>{if(++attempt===1)throw new Error(error);return {application:{...pending,status:'returned',reviewer:admin,reviewedAt:'2026-09-11T11:00:00Z',reason:'请补充示例\n和输入说明'}}}});
 try{assert.match(document.querySelector('[role="alert"]').textContent,/original-log-id/);assert.equal(button('申请公开'),undefined);await act(async()=>button('刷新').click());assert.equal(document.querySelector('[role="alert"]'),null);assert.match(document.body.textContent,/请补充示例\n和输入说明/);assert.ok(button('申请公开'))}finally{await view.close()}
});
test('unpublishing requires a separate confirmation before changing visibility',async()=>{
 const writes=[];const current={...pending,status:'approved',published:true,reviewer:admin,reviewedAt:'2026-09-11T11:00:00Z'};
 const view=await mount({read:async()=>({application:current}),change:async(...args)=>{writes.push(args);return {...current,published:false}}});
 try{await act(async()=>button('取消公开').click());assert.equal(writes.length,0);await act(async()=>button('确认').click());assert.equal(writes[0][1],'unpublish');assert.match(document.body.textContent,/仅自己可见/)}finally{await view.close()}
});
