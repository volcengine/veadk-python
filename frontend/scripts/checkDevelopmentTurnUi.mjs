// Run against a built Studio test server. Sandbox/task HTTP responses are controlled below.
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
import {mkdir, writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const out=process.env.EVIDENCE_DIR || '/tmp/studio-turn-ui-evidence';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE,headless:true,args:['--no-sandbox','--no-proxy-server']});
const page=await browser.newPage({viewport:{width:1440,height:960},colorScheme:'dark'});
const errors=[], requests=[], events=[];
let run=null, nextSeq=1, startedAt=0, firstSubscription=0, breakConnection=0, sourceAttempts=0;
const session={sessionId:'ux-session',status:'Ready',toolName:'intelligent-development',displayName:'构建体验验收',isMine:true,region:'cn-beijing',workspaceLocked:true,busy:false,model:'doubao-seed-2-1-pro-260628'};
const delivery={sessionId:session.sessionId,agentName:'customer_analysis_assistant_with_a_long_project_name',entryPoint:'src/customer_analysis/agents/project_with_very_long_nested_directory_names/assistant_with_a_long_filename_for_preview_verification.py',fileCount:2,artifactSize:20480,artifactSha256:'a'.repeat(64),validationReportSha256:'b'.repeat(64),validatedAt:'2026-09-16T04:00:00Z',gateSummary:['ruff','pytest'],verified:true,deployable:true,validationSummary:'检查通过'};
function emit(type,payload){events.push({type,payload:{...payload,seq:nextSeq++,runId:'ux-run'}});if(run)run.lastSeq=nextSeq-1;}
page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>{localStorage.setItem('veadk_local_user','studio-ux-verification');sessionStorage.setItem('veadk_local_user_tab','studio-ux-verification');localStorage.setItem('agentkit.studio.locale','zh-CN');});
await page.route('**/web/model-options?*',r=>r.fulfill({json:{models:[{id:session.model,name:session.model,available:true,lifecycleStatus:'Active'}]}}));
await page.route('**/web/intelligent-development/**',async route=>{
 const req=route.request(),u=new URL(req.url()),path=u.pathname,method=req.method();requests.push({path,method});
 const json=v=>route.fulfill({json:v});
 if(path.endsWith('/capabilities'))return json({enabled:true,reason:'',model:{configured:true,id:session.model},projectStorageEnabled:true});
 if(path.endsWith('/projects'))return json({projects:[]});
 if(path.endsWith('/releases/summary')){sourceAttempts++;await new Promise(r=>setTimeout(r,400));if(sourceAttempts===1)return route.fulfill({status:503,json:{detail:'预览暂时不可用，请重试'}});return json({...delivery,files:[{path:delivery.entryPoint,content:'print("preview verified")'},{path:'README.md',content:'# Preview project'}]});}
 if(path.endsWith('/sessions')&&method==='POST'){await new Promise(r=>setTimeout(r,900));return json(session);}
 if(path.endsWith('/connect')){await new Promise(r=>setTimeout(r,700));return json(session);}
 if(path.endsWith('/sessions'))return json({sessions:run?[session]:[]});
 if(path.endsWith('/sessions/ux-session/runs')&&method==='POST'){
  const body=req.postDataJSON();await new Promise(r=>setTimeout(r,500));
  run={runId:'ux-run',sessionId:'ux-session',requestId:body.requestId,message:body.message,state:'running',phase:'coding',threadId:'thread-ux',turnId:'turn-ux',lastSeq:0,inputRevision:1,createdAt:Date.now()/1000,statusMessage:'正在处理请求',stopRequested:false};
  emit('run.input',{clientId:body.requestId,message:body.message,status:'delivered'});
  emit('activity',{id:'r1',turnId:'turn-ux',itemType:'reasoning',kind:'thinking',status:'running',text:''});
  startedAt=Date.now();return json(run);
 }
 if(path.endsWith('/runs'))return json({runs:run?[run]:[]});
 if(path.endsWith('/events')){
  if(breakConnection>0){breakConnection--;return route.abort('failed');}
  if(!firstSubscription)firstSubscription=Date.now();
  const after=Number(u.searchParams.get('after')||0);
  return route.fulfill({contentType:'text/event-stream',body:events.filter(e=>e.payload.seq>after).map(e=>`event: ${e.type}\ndata: ${JSON.stringify(e.payload)}\n\n`).join('')+'event: done\ndata: {}\n\n'});
 }
 if(path.endsWith('/inputs')){const body=req.postDataJSON();emit('run.input',{clientId:body.clientId,message:body.message,status:'delivered'});return json({accepted:true});}
 if(path.endsWith('/stop')){emit('development.succeeded',{turnId:'turn-ux',payload:{delivery}});emit('run.turn',{turnId:'turn-ux',status:'interrupted',durationMs:1542277,model:session.model,usageIncomplete:true,usage:{totalTokens:8000,inputTokens:6000,cachedInputTokens:4000,cacheWriteInputTokens:100,outputTokens:2000,reasoningOutputTokens:500}});run={...run,state:'cancelled',phase:'cancelled',statusMessage:'任务已停止',stopRequested:true};emit('run.status',run);return json(run);}
 if(path.endsWith('/runs/ux-run'))return json(run);
 if(path.endsWith('/sessions/ux-session'))return json(session);
 return json({});
});
try{
 await page.goto(process.env.STUDIO_TEST_URL || 'http://127.0.0.1:18080',{waitUntil:'networkidle'});
 await page.getByRole('button',{name:'智能体',exact:true}).click();
 await page.getByText('创建智能体',{exact:true}).click();
 await page.getByRole('button',{name:/传统模式/}).click();
 await page.getByText('智能模式',{exact:true}).click();
 await page.locator('textarea').fill('构建体验验收：保留输出并展示工具过程');

 await page.screenshot({path:out+'/before-start.png'});
 await page.locator('textarea').press('Control+Enter');
 if(await page.locator('.development-preparation').count()===0){
  const buttons=page.getByRole('button',{name:/开始构建|开始创建|构建 Agent/});
  if(await buttons.count())await buttons.first().click();
 }
 await page.waitForSelector('.development-preparation',{timeout:5000});
 await page.screenshot({path:out+'/preparation.png'});
 const samples=[];
 for(let i=0;i<28;i++){
  samples.push(await page.evaluate(()=>({welcome:!!document.querySelector('.welcome'),goal:document.body.innerText.includes('构建体验验收：保留输出并展示工具过程'),preparation:!!document.querySelector('.development-preparation')})));
  await page.waitForTimeout(100);
 }
 assert.ok(samples.every(s=>!s.welcome&&s.goal),'task startup must never flash a welcome or clear the request');
 await page.getByRole('button',{name:'正在思考',exact:true}).waitFor();
 await page.screenshot({path:out+'/initial-thinking.png'});
 const startupGeometry=await page.locator('.turn--user .bubble').first().boundingBox();
 assert.ok(firstSubscription-startedAt<500,`subscription delayed ${firstSubscription-startedAt}ms`);
 const group=page.locator('.development-process__toggle').first();
 assert.equal(await group.getAttribute('aria-expanded'),'false');
 await group.focus();await page.keyboard.press('Enter');
 assert.equal(await group.getAttribute('aria-expanded'),'true');
 emit('activity',{id:'r1',turnId:'turn-ux',itemType:'reasoning',kind:'thinking',status:'done',text:'检查项目结构与验收标准'});
 emit('activity',{id:'c1',turnId:'turn-ux',itemType:'commandExecution',kind:'tool',name:'运行命令',status:'running',args:{command:'python -m pytest --verbose tests/test_a_really_long_command_that_should_never_wrap_the_header.py',commandActions:[{type:'unknown'}]}});
 emit('tool_output',{id:'c1',turnId:'turn-ux',text:'LIVE_LOG_START\n'+Array.from({length:150},(_,i)=>`line ${i} verified`).join('\n')+'\nLIVE_LOG_END'});
 await page.waitForFunction(()=>document.querySelector('.development-process__toggle')?.textContent.includes('执行命令'));
 assert.equal(await group.getAttribute('aria-expanded'),'true');
 const alignment=await page.evaluate(()=>{
  const think=document.querySelector('.think-label').getBoundingClientRect();
  const tool=document.querySelector('.tool-name').getBoundingClientRect();
  return {thinkingX:think.x,toolX:tool.x,toolHeight:tool.height,label:document.querySelector('.tool-name').textContent};
 });
 assert.ok(Math.abs(alignment.thinkingX-alignment.toolX)<1,JSON.stringify(alignment));
 assert.ok(alignment.toolHeight<22);
 assert.equal(alignment.label,'执行命令 · Run tests');
 await page.locator('.tool-head').first().click();
 await page.getByText(/LIVE_LOG_END/).first().waitFor();
 emit('activity',{id:'c1',turnId:'turn-ux',itemType:'commandExecution',kind:'tool',name:'运行命令',status:'error',durationMs:432,response:{exitCode:1,output:'file missing'},args:{command:'python -m pytest --verbose tests/test_a_really_long_command_that_should_never_wrap_the_header.py',commandActions:[{type:'unknown'}]}});
 emit('plan',{turnId:'turn-ux',text:'修复并验证',plan:[{step:'检查项目',status:'completed'},{step:'修复文件',status:'inProgress'}]});
 emit('diff',{turnId:'turn-ux',text:'diff --git a/agent.py b/agent.py\n--- a/agent.py\n+++ b/agent.py\n+fixed = True'});
 emit('delta',{id:'a1',turnId:'turn-ux',itemType:'agentMessage',phase:'commentary',text:'已保留已有输出，正在继续验证。'});
 emit('activity',{id:'m1',turnId:'turn-ux',itemType:'mcpToolCall',kind:'tool',name:'MCP · docs/search',status:'running',args:{query:'validation'}});
 emit('tool_progress',{id:'m1',turnId:'turn-ux',text:'已检索到 3 条参考资料'});
 await page.getByText('已保留已有输出，正在继续验证。',{exact:true}).waitFor();
 assert.equal(await page.locator('.development-process').count(),2);
 assert.doesNotMatch((await page.locator('.tool-head').allInnerTexts()).join('\n'),/毫秒|\bms\b/);
 assert.match(await page.locator('.development-process__duration').first().innerText(),/432 毫秒/);
 assert.ok(await page.locator('.development-diff summary svg').count()>0);
 assert.ok(await page.locator('.plan-icon svg').count()>0);
 await page.locator('.development-diff summary').click();
 await page.screenshot({path:out+'/expanded-desktop.png'});
 await group.click();
 assert.equal(await page.locator('.development-process__failure').count(),0);
 breakConnection=3;
 await page.waitForFunction(()=>/连接|重连/.test(document.querySelectorAll('.development-process__toggle')[1]?.textContent||''),{timeout:10000});
 assert.ok(await page.getByText('已保留已有输出，正在继续验证。',{exact:true}).isVisible());
 const input=page.locator('textarea');await input.fill('补充要求：保留原有文件');
 await input.dispatchEvent('keydown',{key:'Enter',isComposing:true,bubbles:true});assert.equal(await input.inputValue(),'补充要求：保留原有文件');
 const steerRequest=page.waitForRequest(r=>r.url().endsWith('/inputs'));
 await input.press('Enter');await steerRequest;
 await page.waitForFunction(()=>document.querySelectorAll('.turn--user').length===2);
 assert.equal(requests.filter(r=>r.path.endsWith('/inputs')).length,1);
 breakConnection=0;
 await page.getByText('正在处理请求',{exact:true}).last().waitFor();
 await page.screenshot({path:out+'/steer-status.png'});
 await page.getByRole('button',{name:'智能体',exact:true}).click();
 await page.getByRole('button',{name:'返回任务',exact:true}).waitFor();
 await page.getByRole('button',{name:'返回任务',exact:true}).click();
 await page.getByText('正在处理请求',{exact:true}).last().waitFor();
 await page.getByRole('button',{name:'返回任务',exact:true}).waitFor({state:'hidden'});
 emit('activity',{id:'m1',turnId:'turn-ux',itemType:'mcpToolCall',kind:'tool',name:'MCP · docs/search',status:'done',durationMs:0});
 await page.getByRole('button',{name:'停止生成',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('.sandbox-codex-composer button[aria-label="停止生成"]'));
 assert.ok(await page.getByText('已保留已有输出，正在继续验证。',{exact:true}).isVisible());
 await page.locator('.development-turn-summary').waitFor();
 const summary=page.locator('.development-turn-summary');
 assert.match(await summary.innerText(),/2 次工具调用/);
 assert.equal(await page.locator('.turn-empty').count(),0);
 assert.match(await summary.innerText(),/25 分 42\.3 秒/);
 assert.match(await summary.innerText(),/432 毫秒/);
 assert.match(await page.locator('.development-process__duration').last().innerText(),/<1 毫秒/);
 const tokens=summary.getByRole('button');
 assert.equal(await tokens.evaluate(el=>getComputedStyle(el).borderTopWidth),'0px');
 await tokens.hover();
 await page.locator('.development-token-popup').waitFor();
 let detail=await page.locator('.development-token-popup').innerText();
 assert.ok(detail.includes(session.model));
 assert.match(detail,/未命中输入\s+2,000/);
 assert.match(detail,/66.7%/);
 await page.screenshot({path:out+'/token-details-desktop.png'});
 await page.keyboard.press('Escape');
 await page.locator('.development-token-popup').waitFor({state:'hidden'});
 await page.mouse.move(0,0);
 await tokens.focus();
 await page.locator('.development-token-popup').waitFor();
 await page.keyboard.press('Escape');
 await page.locator('.development-token-popup').waitFor({state:'hidden'});
 await page.keyboard.press('Enter');
 await page.locator('.development-token-popup').waitFor();
 await page.keyboard.press('Escape');
 const card=page.locator('.delivery-card');await card.waitFor();
 assert.equal(await card.locator('strong').innerText(),delivery.agentName);
 assert.equal(await card.locator('.delivery-card-entry dd').innerText(),delivery.entryPoint);
 await card.scrollIntoViewIfNeeded();await page.screenshot({path:out+'/delivery-desktop.png'});
 const sourceButton=card.getByRole('button',{name:'查看源码',exact:true});
 await sourceButton.click();assert.equal(await sourceButton.isDisabled(),true);
 await card.getByRole('alert').waitFor();assert.equal(await sourceButton.isEnabled(),true);
 await sourceButton.click();await page.locator('.code-browser-dialog').waitFor();
 await page.keyboard.press('Escape');await page.locator('.code-browser-dialog').waitFor({state:'hidden'});
 await page.setViewportSize({width:820,height:900});await page.emulateMedia({reducedMotion:'reduce'});
 await tokens.hover();await page.locator('.development-token-popup').waitFor();await page.screenshot({path:out+'/stopped-narrow.png'});
 const layout=await page.evaluate(()=>({width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth}));assert.ok(layout.scrollWidth<=layout.width);
 await page.keyboard.press('Escape');await page.setViewportSize({width:600,height:900});await card.scrollIntoViewIfNeeded();
 const cardLayout=await card.evaluate(el=>({width:el.clientWidth,scrollWidth:el.scrollWidth,entryHeight:el.querySelector('.delivery-card-entry dd').getBoundingClientRect().height}));
 assert.ok(cardLayout.scrollWidth<=cardLayout.width);assert.ok(cardLayout.entryHeight>18);
 await page.screenshot({path:out+'/delivery-narrow.png'});
 assert.deepEqual(errors,[]);
 await writeFile(out+'/browser.json',JSON.stringify({alignment,turnSummary:await summary.innerText(),tokenDetails:detail,startupGeometry,startupSamples:samples,subscriptionDelayMs:firstSubscription-startedAt,keyboardDisclosure:true,expansionPreserved:true,toolLogEndVisible:true,planAndDiff:true,reconnectPreservesOutput:true,steer:true,backgroundNoticeReturn:true,stop:true,ime:true,layout,pageErrors:errors,apiBoundary:'controlled Codex event and Sandbox API responses; actual built App, HTTP client, hook, projection and UI'},null,2));
 console.log('Browser journey passed');
}catch(e){await page.screenshot({path:out+'/browser-failure.png'});console.log('failure body', (await page.locator('body').innerText()).slice(-4000));throw e;}
finally{await browser.close();}
