import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import { JSDOM } from "jsdom";
const require = createRequire(import.meta.url);
const React = require("react");
const {act} = React;
const translations = JSON.parse(readFileSync(new URL("../src/i18n/resources/zh-CN/reviews.json", import.meta.url), "utf8"));
const agentTranslations = JSON.parse(readFileSync(new URL("../src/i18n/resources/zh-CN/agentReviews.json", import.meta.url), "utf8"));
const mocks = {
  "react-i18next": `const catalog = { reviews: ${JSON.stringify(translations)}, agentReviews: ${JSON.stringify(agentTranslations)} };
    const translate = (namespace) => (key, options = {}) => { const resources = catalog[namespace]; const value = key.split('.').reduce((obj, part) => obj?.[part], resources); return (typeof value === 'string' ? value : key).replace(/{{(\\w+)}}/g, (_, name) => options[name] ?? ''); };
    const translators = Object.fromEntries(Object.keys(catalog).map(key => [key, translate(key)]));
    export const useTranslation = (namespace = "reviews") => ({t: translators[namespace], i18n:{language:'zh-CN'}});`,
  "../adk/agentReviews": `export const listAgentReviews = (...args) => globalThis.agentReviewApi.list(...args); export const readAgentReview = (...args) => globalThis.agentReviewApi.read(...args); export const changeAgentReview = (...args) => globalThis.agentReviewApi.change(...args);`,
  "../adk/skills": `export const listSkillReviews = (...args) => globalThis.reviewApi.list(...args); export const getSkillReviewFiles = (...args) => globalThis.reviewApi.files(...args); export const decideSkillReview = (...args) => globalThis.reviewApi.decide(...args);`,
  "../adk/reviewScores": `export const getReviewScore = (...args) => globalThis.scoreApi.get(...args); export const retryReviewScore = (...args) => globalThis.scoreApi.retry(...args);`,
  "../ui/text-shimmer/TextShimmer": `import {createElement as h} from 'react'; export const TextShimmer = ({children}) => h('span',null,children);`,
  "../adk/cloudProvider": `export const defaultCloudRegion = () => 'cn-beijing'; export const formatCloudRegion = value => value; export const cloudRegionOptions = () => [{value:'cn-beijing',label:'北京'},{value:'cn-shanghai',label:'上海'}];`,
  "../ui/skills/SkillErrorDetails": `import {createElement as h} from 'react'; export const normalizeSkillError = value => value; export const SkillErrorDetails = ({error}) => h('span',null,error.message);`,
  "../ui/skills/SkillFileTree": `import {createElement as h} from 'react'; export const SkillFileTree = ({files}) => h('pre',null,files.map(file => file.content).join('\\n'));`,
  "@openai/apps-sdk-ui/components/Button": `import {createElement as h} from 'react'; export const Button = ({children,disabled,onClick}) => h('button',{disabled,onClick},children);`,
  "@base-ui/react/dialog": `import {createElement as h} from 'react'; const Box=({children})=>h('div',null,children); export const Dialog={Root:Box,Portal:Box,Backdrop:Box,Popup:Box,Title:Box,Description:Box,Close:Box};`,
  "../ui/ResourceCollection": `import {createElement as h} from 'react';
    const Box=({children})=>h('div',null,children);
    export const ResourcePageShell=Box, ResourceToolbar=Box;
    export const ResourcePageHeader=({title})=>h('h1',null,title);
    export const ResourceLoadingState=()=>h('span',{role:'status'},'加载中');
    export const ResourceTabs=({items,onChange})=>h('div',null,...items.map(item=>h('button',{key:item.id,onClick:()=>onChange(item.id)},item.label)));
    export const ResourceFilterSelect=({options,value,onChange,ariaLabel})=>h('select',{'aria-label':ariaLabel,value,onChange:event=>onChange(event.target.value)},...options.map(item=>h('option',{key:item.value,value:item.value},item.label)));
    export const ResourceDataTable=({rows,columns,rowKey,toolbarActions,emptyLabel})=>h('div',null,toolbarActions,h('table',null,h('tbody',null,...rows.map(row=>h('tr',{'data-row':rowKey(row),key:rowKey(row)},...columns.map(column=>h('td',{key:column.key},column.render(row))))))),rows.length?null:emptyLabel);`,
};
const result = await build({
  stdin:{contents:"export { ReviewCenter } from './src/reviews/ReviewCenter'; export { ReviewHistoryList } from './src/reviews/ReviewOutcome'; export { ReviewScoreDetails, ReviewScoreLabel } from './src/reviews/ReviewScore';",resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'tsx'}, bundle:true,format:'cjs',platform:'node',write:false,
  external:['react','react-dom','react-dom/*'],
  plugins:[{name:'review-test',setup(builder){
    builder.onResolve({filter:/.*/},({path})=>path in mocks?{path,namespace:'mock'}:path.endsWith('.css')?{path,namespace:'empty'}:undefined);
    builder.onLoad({filter:/.*/,namespace:'mock'},({path})=>({contents:mocks[path]}));
    builder.onLoad({filter:/.*/,namespace:'empty'},()=>({contents:''}));
  }}],
});
const module={exports:{}};
Function('require','module','exports',result.outputFiles[0].text)(require,module,module.exports);
const {ReviewCenter,ReviewHistoryList,ReviewScoreDetails,ReviewScoreLabel}=module.exports;
const requests=[
  {id:'copy-a',kind:'skill',name:'same-name',description:'实际说明',author:'申请人甲',version:'v3',reviewVersion:'v1',submittedAt:'2026-09-11T08:00:00Z',region:'cn-beijing',status:'pending'},
  {id:'copy-b',kind:'skill',name:'same-name',description:'实际说明',author:'申请人乙',version:'v2',reviewVersion:'v1',submittedAt:'2026-09-11T08:00:00Z',region:'cn-beijing',status:'pending'},
];
async function mount(api,role='admin',Component=ReviewCenter,props={}) {
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true,reviewApi:api});
  Object.defineProperty(globalThis,'navigator',{value:dom.window.navigator,configurable:true});
  const {createRoot}=require('react-dom/client');
  const root=createRoot(document.getElementById('root'));
  await act(async()=>root.render(React.createElement(Component,{role,cloudProvider:'volcengine',...props})));
  return async()=>{await act(async()=>root.unmount());dom.window.close();};
}
const button=name=>[...document.querySelectorAll('button')].find(item=>item.textContent===name);
test('ordinary users cannot fetch review requests',async()=>{
  let called=false;
  const close=await mount({list:()=>{called=true;}},'user');
  try {assert.equal(called,false);assert.match(document.body.textContent,/仅管理员/);} finally {await close();}
});
test('admin sees separate same-name requests and the actual submitted files',async()=>{
  let fileId;
  const close=await mount({list:async()=>({items:requests}),files:async({id})=>{fileId=id;return {files:[{path:'SKILL.md',content:'真实提交文件内容',size:24,kind:'text'}]};}});
  try {
    assert.equal(document.querySelectorAll('tr').length,2);
    assert.match(document.body.textContent,/申请人甲/);assert.match(document.body.textContent,/申请人乙/);
    assert.equal(button('通过').disabled,false);
    await act(async()=>button('详情').click());
    await act(async()=>button('提交文件').click());
    assert.equal(fileId,'copy-a');assert.match(document.body.textContent,/真实提交文件内容/);
    assert.doesNotMatch(document.body.textContent,/示例申请|示例文件/);
  } finally {await close();}
});
test('a failed list reports the error and retries',async()=>{
  let calls=0;
  const close=await mount({list:async()=>{if(++calls===1)throw new Error('连接失败');return {items:requests};}});
  try {
    assert.match(document.querySelector('[role="alert"]').textContent,/连接失败/);
    await act(async()=>button('重试').click());
    assert.equal(document.querySelectorAll('tr').length,2);
  } finally {await close();}
});

async function inputText(id, value) {
  const field=document.getElementById(id);
  const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
  await act(async()=>{
    setter.call(field,value);
    field.dispatchEvent(new window.Event('input',{bubbles:true}));
  });
}
test('approval sends its comment and shows the persisted reviewer profile and time',async()=>{
  let payload;
  const reviewer={id:'admin-id',name:'审核管理员',email:'reviewer@example.test',avatarUrl:'https://example.test/avatar.png'};
  const close=await mount({list:async()=>({items:[requests[0]]}),decide:async(args)=>{
    payload=args;
    return {...requests[0],status:'approved',reviewedBy:'旧名称',reviewer,reviewedAt:'2026-09-11T09:00:00Z',comment:args.comment};
  }});
  try {
    await act(async()=>button('通过').click());
    await inputText('review-decision-comment','说明完整，可以公开');
    await act(async()=>button('确认通过').click());
    assert.equal(payload.decision,'approved');
    assert.equal(payload.comment,'说明完整，可以公开');
    assert.match(document.body.textContent,/已通过并公开/);
    assert.equal(button('通过'),undefined);
    assert.equal(button('退回'),undefined);
    assert.match(document.body.textContent,/审核管理员/);
    await act(async()=>button('详情').click());
    assert.match(document.body.textContent,/reviewer@example.test/);
    assert.match(document.body.textContent,/说明完整，可以公开/);
    assert.match(document.body.textContent,/通过人/);
    assert.ok(document.querySelector('time[datetime="2026-09-11T09:00:00Z"]'));
    assert.equal(document.querySelector('.review-outcome img').getAttribute('src'),reviewer.avatarUrl);
    await act(async()=>document.querySelector('.review-outcome img').dispatchEvent(new window.Event('error')));
    assert.equal(document.querySelector('.review-outcome img'),null);
    assert.match(document.querySelector('.review-outcome').textContent,/审核管理员/);
  } finally {await close();}
});
test('return requires a reason and preserves reason and comment separately',async()=>{
  let payload;
  const close=await mount({list:async()=>({items:[requests[0]]}),decide:async(args)=>{
    payload=args;return {...requests[0],status:'returned',reviewedBy:'管理员',reviewedAt:'2026-09-11T09:00:00Z',reason:args.reason,comment:args.comment};
  }});
  try {
    await act(async()=>button('退回').click());
    assert.equal(button('确认退回').disabled,true);
    assert.equal(document.getElementById('review-return-reason').maxLength,256);
    assert.equal(document.getElementById('review-decision-comment').maxLength,256);
    await inputText('review-return-reason','  ');
    assert.equal(button('确认退回').disabled,true);
    await inputText('review-return-reason','缺少输入示例');
    await inputText('review-decision-comment','请补充后重新提交');
    await act(async()=>button('确认退回').click());
    assert.equal(payload.reason,'缺少输入示例');
    assert.equal(payload.comment,'请补充后重新提交');
    await act(async()=>button('详情').click());
    assert.match(document.body.textContent,/退回人/);
    assert.match(document.body.textContent,/缺少输入示例/);
    assert.match(document.body.textContent,/请补充后重新提交/);
  } finally {await close();}
});
test('failed approval keeps the comment for retry and prevents duplicate requests while saving',async()=>{
  let calls=0,resolve;
  const close=await mount({list:async()=>({items:[requests[0]]}),decide:async(args)=>{
    if(++calls===1)throw new Error('标签保存失败');
    return new Promise(done=>{resolve=()=>done({...requests[0],status:'approved',comment:args.comment});});
  }});
  try {
    await act(async()=>button('通过').click());
    await inputText('review-decision-comment','已检查');
    await act(async()=>button('确认通过').click());
    assert.match(document.querySelector('[role="alert"]').textContent,/标签保存失败/);
    assert.equal(document.getElementById('review-decision-comment').value,'已检查');
    await act(async()=>button('确认通过').click());
    assert.equal(button('处理中…').disabled,true);
    await act(async()=>button('处理中…').click());
    assert.equal(calls,2);
    await act(async()=>resolve());
    assert.match(document.body.textContent,/已通过并公开/);
  } finally {await close();}
});
test('unfinished publication can resume and cannot be returned',async()=>{
  let payload;
  const application={...requests[0],status:'approving',comment:'已确认',reviewedBy:'管理员',reviewedAt:'2026-09-11T09:00:00Z'};
  const close=await mount({list:async()=>({items:[application]}),decide:async(args)=>{payload=args;return {...application,status:'approved'};}});
  try {
    assert.equal(button('退回'),undefined);
    await act(async()=>button('继续发布').click());
    assert.equal(document.getElementById('review-decision-comment').value,'已确认');
    assert.equal(document.getElementById('review-decision-comment').disabled,true);
    await act(async()=>button('确认通过').click());
    assert.equal(payload.comment,'已确认');
    assert.equal(payload.decision,'approved');
  } finally {await close();}
});

test('the applicant history retains previous returns and separates versions',async()=>{
  const applications=[
    {...requests[0],id:'first-return',version:'v1',status:'returned',submittedAt:'2026-09-10T08:00:00Z',reviewedBy:'初审管理员',reason:'缺少示例',comment:'补充后再提交'},
    {...requests[0],id:'approved-v1',version:'v1',status:'approved',submittedAt:'2026-09-11T08:00:00Z',reviewer:{id:'admin',name:'终审管理员',email:'admin@example.test'},comment:'示例已补充'},
    {...requests[0],id:'pending-v2',version:'v2',status:'pending',submittedAt:'2026-09-12T08:00:00Z'},
  ];
  const close=await mount({},'user',ReviewHistoryList,{applications});
  try {
    const records=[...document.querySelectorAll('.review-source-history > li')];
    assert.equal(records.length,3);
    assert.match(records[0].textContent,/v2.*待审核/);
    assert.match(records[1].textContent,/v1.*已通过.*终审管理员.*admin@example.test.*示例已补充/);
    assert.match(records[2].textContent,/已退回.*初审管理员.*缺少示例.*补充后再提交/);
  } finally {await close();}
});
test('IME and Enter keep text input local until the explicit decision button is clicked',async()=>{
  let calls=0;
  const close=await mount({list:async()=>({items:[requests[0]]}),decide:async()=>{calls++;return {...requests[0],status:'approved'};}});
  try {
    await act(async()=>button('通过').click());
    const field=document.getElementById('review-decision-comment');
    await act(async()=>{
      field.dispatchEvent(new window.CompositionEvent('compositionstart',{bubbles:true}));
      field.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Enter',keyCode:229,isComposing:true,bubbles:true}));
      field.dispatchEvent(new window.CompositionEvent('compositionend',{bubbles:true}));
      field.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
    });
    assert.equal(calls,0);
    await act(async()=>button('确认通过').click());
    assert.equal(calls,1);
  } finally {await close();}
});

const scoreResult = {
  applicationId:'copy-a',skillName:'same-name',skillVersion:'v3',provider:'volcengine',
  rubricVersion:'1',modelName:'shared-planning-model',scoredAt:'2026-09-11T12:00:00Z',overallScore:null,
  dimensions:{
    safety:{score:0,reason:'scripts/run.sh 存在未经确认的删除操作'},
    usability:{score:80,reason:'SKILL.md 有明确的使用示例'},
    completeness:{score:null,reason:'引用的配置文件未包含在提交内容中'},
    reliability:{score:70,reason:'未说明超时处理'},
    maintainability:{score:90,reason:'步骤结构清晰'},
  },
  riskFlags:[{severity:'critical',reason:'未经确认执行删除'}],suggestions:['补充配置和超时处理'],
  coverage:{complete:false,totalFiles:3,includedFiles:1,omittedFiles:[{path:'model.bin',reason:'二进制文件'}],truncatedFiles:[{path:'scripts/run.sh',reason:'文件过长'}]},
};
const scored = {status:'completed',overallScore:null,result:scoreResult};

test('score labels distinguish zero, insufficient evidence, pending and absent scores',async()=>{
  for(const [score,expected] of [[{status:'completed',overallScore:0},'0 分'],[{status:'completed',overallScore:null},'依据不足'],[{status:'queued'},'等待评分'],[{status:'failed'},'评分失败'],[undefined,'尚未评分']]){
    const close=await mount({},'user',ReviewScoreLabel,{score});
    try{assert.equal(document.body.textContent,expected);}finally{await close();}
  }
});

test('score details render dimensions, risk severity and coverage and export the original JSON',async()=>{
  globalThis.scoreApi={get:async()=>scored};
  const close=await mount({},'user',ReviewScoreDetails,{application:{...requests[0],aiReview:{status:'completed',overallScore:null}}});
  try{
    const content=document.body.textContent;
    assert.match(content,/安全性0 分/);
    assert.match(content,/完整性依据不足/);
    assert.match(content,/严重风险.*未经确认执行删除/);
    assert.match(content,/model.bin.*二进制文件/);
    assert.match(content,/scripts\/run.sh.*文件过长/);
    assert.match(content,/shared-planning-model/);
    assert.equal(document.querySelectorAll('.review-score__dimensions > div').length,5);
    assert.equal(button('重新评分'),undefined);
    const download=document.querySelector('a[download]');
    const json=await fetch(download.href).then(response=>response.json());
    assert.deepEqual(json,scoreResult);
  }finally{await close();}
});

test('applicant score history lazily loads only the expanded submission',async()=>{
  const fetched=[];
  globalThis.scoreApi={get:async({id})=>{fetched.push(id);return scored;}};
  const close=await mount({},'user',ReviewHistoryList,{applications:[
    {...requests[0],aiReview:{status:'completed',overallScore:84}},
    {...requests[1],aiReview:{status:'queued'}},
  ]});
  try{
    assert.deepEqual(fetched,[]);
    await act(async()=>document.querySelector('.review-score-history__toggle').click());
    assert.deepEqual(fetched,['copy-a']);
    assert.equal(document.querySelector('.review-score-history__toggle').getAttribute('aria-expanded'),'true');
    assert.match(document.body.textContent,/安全性0 分/);
    assert.equal(button('重新评分'),undefined);
    await act(async()=>document.querySelector('.review-score-history__toggle').click());
    assert.equal(document.querySelector('.review-score'),null);
  }finally{await close();}
});

test('score load errors remain visible and reload does not request a new scoring job',async()=>{
  let gets=0,retries=0;
  globalThis.scoreApi={get:async()=>{if(++gets===1)throw new Error('读取评分失败');return scored;},retry:async()=>{retries++;}};
  const close=await mount({},'user',ReviewScoreDetails,{application:{...requests[0],aiReview:{status:'completed'}}});
  try{
    assert.match(document.querySelector('[role="alert"]').textContent,/读取评分失败/);
    await act(async()=>button('重新加载').click());
    assert.equal(gets,2);assert.equal(retries,0);
    assert.match(document.body.textContent,/安全性0 分/);
  }finally{await close();}
});

test('admin can retry failed scoring and repeated clicks are disabled during submission',async()=>{
  let resolve,retries=0;
  globalThis.scoreApi={get:async()=>({status:'failed',error:'评分模型请求超时'}),retry:async()=>{retries++;return new Promise(done=>{resolve=done;});}};
  const close=await mount({},'admin',ReviewScoreDetails,{application:{...requests[0],aiReview:{status:'failed'}},canRetry:true});
  try{
    assert.match(document.body.textContent,/评分模型请求超时/);
    await act(async()=>button('重新评分').click());
    assert.equal(button('重新评分').disabled,true);
    await act(async()=>button('重新评分').click());
    assert.equal(retries,1);
    await act(async()=>resolve({status:'queued'}));
    assert.match(document.body.textContent,/等待评分/);
    assert.equal(button('重新评分'),undefined);
  }finally{await close();}
});

test('admin can score a legacy submission while an applicant cannot start a job',async()=>{
  let retries=0;
  globalThis.scoreApi={get:async()=>({status:'not_requested'}),retry:async()=>{retries++;return {status:'queued'};}};
  let close=await mount({},'user',ReviewScoreDetails,{application:requests[0]});
  try{assert.match(document.body.textContent,/尚未评分/);assert.equal(button('开始评分'),undefined);}finally{await close();}
  close=await mount({},'admin',ReviewScoreDetails,{application:requests[0],canRetry:true});
  try{
    await act(async()=>button('开始评分').click());
    assert.equal(retries,1);assert.match(document.body.textContent,/等待评分/);
  }finally{await close();}
});

test('closing score details aborts the request and ignores its late response',async()=>{
  let signal,resolve;
  globalThis.scoreApi={get:async(args)=>{signal=args.signal;return new Promise(done=>{resolve=done;});}};
  const close=await mount({},'user',ReviewScoreDetails,{application:{...requests[0],aiReview:{status:'running'}}});
  assert.match(document.body.textContent,/加载评分/);
  await close();
  assert.equal(signal.aborted,true);
  await act(async()=>resolve(scored));
});

test('score polling pauses in hidden tabs, resumes when visible and stops on completion',async()=>{
  let gets=0;
  globalThis.scoreApi={get:async()=>++gets===1?{status:'running'}:scored};
  const close=await mount({},'user',ReviewScoreDetails,{application:{...requests[0],aiReview:{status:'queued'}}});
  try{
    Object.defineProperty(document,'visibilityState',{value:'hidden',configurable:true});
    assert.equal(gets,1);
    await act(async()=>document.dispatchEvent(new window.Event('visibilitychange')));
    assert.equal(gets,1);
    Object.defineProperty(document,'visibilityState',{value:'visible',configurable:true});
    await act(async()=>document.dispatchEvent(new window.Event('visibilitychange')));
    assert.equal(gets,2);
    await act(async()=>document.dispatchEvent(new window.Event('visibilitychange')));
    assert.equal(gets,2);
    assert.match(document.body.textContent,/安全性0 分/);
  }finally{await close();}
});

test('review list shows scoring progress without disabling manual approval and loads reports only on selection',async()=>{
  let gets=0;
  globalThis.scoreApi={get:async()=>{gets++;return {status:'running'};}};
  const close=await mount({list:async()=>({items:[{...requests[0],aiReview:{status:'running'}}]})});
  try{
    assert.match(document.body.textContent,/评分中/);assert.equal(button('通过').disabled,false);assert.equal(gets,0);
    await act(async()=>button('详情').click());
    assert.equal(gets,0);
    await act(async()=>button('AI 评分').click());
    assert.equal(gets,1);
  }finally{await close();}
});

test('the complete persisted cloud error retains request IDs and line breaks without truncation',async()=>{
  const raw='Error code: 400\n'+JSON.stringify({error:{code:'InvalidParameter',message:'错误详情'.repeat(500)},RequestId:'20260911-original-cloud-request-id'},null,2)+'\nUpstream trace details';
  globalThis.scoreApi={get:async()=>({status:'failed',error:raw})};
  const close=await mount({},'user',ReviewScoreDetails,{application:{...requests[0],aiReview:{status:'failed'}}});
  try{
    const details=document.querySelector('.review-score__raw-error');
    assert.equal(details.open,true);
    assert.equal(details.querySelector('pre').textContent,raw);
    assert.match(details.textContent,/20260911-original-cloud-request-id/);
    assert.equal(button('重新评分'),undefined);
  }finally{await close();}
});

test('completed scores are read-only even for administrators',async()=>{
  let retries=0;
  globalThis.scoreApi={get:async()=>scored,retry:async()=>{retries++;return {status:'queued'};}};
  const close=await mount({},'admin',ReviewScoreDetails,{application:{...requests[0],aiReview:{status:'completed'}},canRetry:true});
  try{
    assert.equal(button('重新评分'),undefined);
    assert.equal(button('开始评分'),undefined);
    assert.equal(retries,0);
    assert.ok(document.querySelector('a[download]'));
  }finally{await close();}
});

test('completed reports retain their score and display persistence errors in full',async()=>{
  const raw='TagResources failed\n'+JSON.stringify({RequestId:'score-tag-save-request',Error:{Code:'InternalError',Message:'标签保存失败'}},null,2);
  globalThis.scoreApi={get:async()=>({...scored,error:raw})};
  const close=await mount({},'admin',ReviewScoreDetails,{application:{...requests[0],aiReview:{status:'completed'}},canRetry:true});
  try{
    assert.equal(document.querySelector('.review-score__raw-error pre').textContent,raw);
    assert.equal(document.querySelectorAll('.review-score__dimensions > div').length,5);
    assert.match(document.body.textContent,/安全性0 分/);
    assert.ok(document.querySelector('a[download]'));
    assert.equal(button('重新评分'),undefined);
  }finally{await close();}
});


test('the Agent tab loads real applications and persists an approval independently of Skills', async () => {
  const person = {id:'developer', name:'智能体开发者', avatarUrl:'', email:''};
  let application = {id:'agent-request', runtimeId:'runtime-agent', region:'cn-beijing', status:'pending', agent:{name:'会议助手', description:'整理会议行动项', version:1, model:'demo-model'}, submitter:person, submittedAt:'2026-09-11T08:00:00Z', message:'请审核', reviewer:null, reviewedAt:'', reason:'', comment:'', published:false};
  let calls = 0;
  globalThis.agentReviewApi = {
    list: async () => { calls++; return {items:[application]}; },
    read: async () => ({application}),
    change: async (runtimeId, action, body) => {
      assert.equal(runtimeId, 'runtime-agent');
      assert.equal(action, 'decision');
      assert.equal(body.applicationId, application.id);
      application = {...application, status:body.decision, published:true, reviewer:{...person,name:'审核管理员'}, reviewedAt:'2026-09-11T09:00:00Z', comment:body.comment};
      return application;
    },
  };
  const close = await mount({list:async()=>({items:requests})});
  try {
    assert.equal(calls, 0);
    await act(async()=>button('智能体').click());
    assert.equal(calls, 1);
    assert.match(document.body.textContent, /会议助手/);
    assert.doesNotMatch(document.body.textContent, /申请人甲/);
    await act(async()=>button('查看并审批').click());
    await act(async()=>button('通过').click());
    assert.equal(application.status, 'approved');
    assert.match(document.body.textContent, /审核管理员/);
    assert.ok(calls >= 2);
  } finally { await close(); }
});
