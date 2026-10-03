'use strict';
const $ = (selector, parent=document) => parent.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusNames={pending:'待开始',in_progress:'进行中',done:'已做完',submitted:'已提交',cancelled:'已取消'};
const kindNames={assignment:'作业',experiment:'实验',exam:'考试',project:'项目',other:'其他'};
let token='', state={tasks:[],proposals:[],messages:[],summary:{},agent:{mode:'rules'}},settings={};
let view='today', inboxTab='pending', month=new Date(),detailId=null,toastTimer;
const filters={search:'',course:'',status:'active'};
const content=$('#content');
function cnLocalTime(date=new Date()){return new Date(date.getTime()+8*3600000).toISOString().slice(0,16)}
function formatDeadline(value){
  if(!value)return '截止待明确';
  const date=value.slice(0,10).replaceAll('-','.');
  return value.length===10 ? date+'（时刻未明确）' : date+' '+value.slice(11,16);
}
function dateLabel(value){return value ? value.slice(0,10).replaceAll('-','.')+' '+value.slice(11,16) : ''}
function dueLabel(task){
  if(!task.deadline)return {text:'截止待明确',color:'amber'};
  if(task.status==='submitted')return {text:'已手动确认提交',color:'green'};
  if(task.status==='cancelled')return {text:'已取消',color:''};
  if(task.deadline.length===10){
    const today=cnLocalTime().slice(0,10);
    return {text:task.deadline<today?'日期已过':task.deadline===today?'今天截止 · 时刻待核对':'日期截止 · 时刻待核对',color:task.deadline<today?'red':'amber'};
  }
  const hours=(new Date(task.deadline)-Date.now())/3600000;
  return hours<=0 ? {text:'已逾期',color:'red'} : hours<24 ? {text:hours<1?'不足 1 小时截止':Math.ceil(hours)+' 小时后截止',color:hours<2?'red':'amber'} : {text:Math.ceil(hours/24)+' 天后截止',color:'green'};
}
function pill(text,color=''){return `<span class="pill ${esc(color)}">${esc(text)}</span>`}
function toast(message,error=false){
  clearTimeout(toastTimer);const box=$('#toast');box.textContent=message;box.className='toast'+(error?' error':'');box.hidden=false;
  toastTimer=setTimeout(()=>box.hidden=true,5500);
}
async function api(path,options={}){
  const headers={...options.headers,Authorization:'Bearer '+token};
  if(options.body!==undefined){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body)}
  const response=await fetch(path,{...options,headers});
  if(!response.ok){let result;try{result=await response.json()}catch{result={error:'服务返回了无效响应。'}}throw new Error(result.error||'请求失败')}
  return response;
}
async function json(path,options){return (await api(path,options)).json()}
async function busy(button,fn){
  if(!button || button.disabled)return;
  const old=button.innerHTML;button.disabled=true;button.textContent='处理中…';
  try{return await fn()}finally{button.disabled=false;button.innerHTML=old}
}
async function refresh(render=true){
  state=await json('/api/state');
  $('#taskBadge').textContent=state.summary.active;
  $('#inboxBadge').textContent=state.proposals.length;
  $('#modeName').textContent=state.agent.mode==='agent'?'模型工具调用模式':'本地规则模式';
  $('#modeHint').textContent=state.agent.description;
  $('.sync-label').innerHTML='<span class="local-dot"></span>本地已连接';
  if(render)renderView();
}
function intro(title,subtitle,eyebrow='MY LEARNING DESK'){
  const now=new Date();
  return `<div class="page-intro"><div><span class="eyebrow">${esc(eyebrow)}</span><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="date-block"><strong>${esc(new Intl.DateTimeFormat('zh-CN',{month:'long',day:'numeric',weekday:'long',timeZone:'Asia/Shanghai'}).format(now))}</strong><span>MAKE ROOM FOR LEARNING</span></div></div>`;
}
function empty(title,text,button=''){
  return `<div class="empty-state"><span class="empty-icon">◇</span><h3>${esc(title)}</h3><p>${esc(text)}</p>${button}</div>`;
}
function taskOptions(selected){return Object.entries(statusNames).map(([v,n])=>`<option value="${v}" ${selected===v?'selected':''}>${n}</option>`).join('')}
function priority(task){
  const due=dueLabel(task);
  return `<div class="priority-item"><span class="course-icon">${esc((task.course||'任务').slice(0,2))}</span><div class="priority-body"><h3>${esc(task.title)}</h3><p>${esc(task.scope||'未设置班级')} · ${esc(kindNames[task.kind])} ${task.sample?'· 示例':''}</p><div class="priority-meta">${pill(task.course||'未填写课程','outline')}${pill(due.text,due.color)}${task.status==='done'?pill('已做完 · 待提交','amber'):''}</div></div><button class="priority-action" data-detail="${task.id}" aria-label="查看 ${esc(task.title)}">↗</button></div>`;
}
function renderToday(){
  const s=state.summary,active=state.tasks.filter(t=>!['submitted','cancelled'].includes(t.status));
  const preview=state.proposals.slice(0,3).map(p=>{const c=p.candidate;return `<div class="review-preview">${pill(c.operation==='update'?'截止变更':c.deadline?'新任务':'截止未明确',c.operation==='update'?'green':'amber')}<h3>${esc(c.course||'课程待填写')} · ${esc(c.title)}</h3><p>${esc(p.before?formatDeadline(p.before.deadline)+' → '+formatDeadline(c.deadline):formatDeadline(c.deadline))}</p><button class="text-button" data-view="inbox">核对原文并确认 ↗</button></div>`}).join('');
  content.innerHTML=intro('把通知，变成清晰的下一步。','课程消息有出处，截止时间不遗漏。')+
    `<section class="hero"><div><span class="hero-label">A LITTLE CLARITY, EVERY DAY</span><h2>${s.pending_reviews?'有 '+s.pending_reviews+' 条任务草稿等你核对':'今天，从整理好一条通知开始'}</h2><p>${s.pending_reviews?'确认课程、材料和截止时间，让每一次变更都有依据。':'粘贴学习通、课程群或教务通知，把任务收进一个地方。'}</p></div><div class="hero-right"><div class="hero-number">${s.pending_reviews||'01'}<small>${s.pending_reviews?'待确认草稿':'一个清晰的开始'}</small></div><button class="button primary" ${s.pending_reviews?'data-view="inbox"':'data-open-import'}>${s.pending_reviews?'打开收件箱':'导入第一条通知'} <span>↗</span></button></div></section>
    <div class="stats-grid"><article class="stat"><div class="stat-top"><span>尚未提交</span><span class="stat-symbol">☑</span></div><div class="stat-number">${s.active}<small>项任务</small></div><p class="stat-note">已做完的任务仍需确认提交</p></article><article class="stat"><div class="stat-top"><span>未来 7 天截止</span><span class="stat-symbol">▦</span></div><div class="stat-number">${s.upcoming}<small>项任务</small></div><p class="stat-note">给临近截止留出准备时间</p></article><article class="stat ${s.overdue?'danger':''}"><div class="stat-top"><span>已经逾期</span><span class="stat-symbol">◷</span></div><div class="stat-number">${s.overdue}<small>项任务</small></div><p class="stat-note">依据已确认的截止时间</p></article><article class="stat"><div class="stat-top"><span>已确认提交</span><span class="stat-symbol">↗</span></div><div class="stat-number">${s.submitted}<small>项任务</small></div><p class="stat-note">由你手动记录，不代表平台回执</p></article></div>
    <div class="two-columns"><section class="panel"><div class="panel-head"><div class="panel-title"><h2>接下来，先做这些</h2><small>${active.length}</small></div><button class="text-button" data-view="tasks">全部任务 ↗</button></div>${active.length?active.slice(0,4).map(priority).join(''):empty('待办还很清爽','导入真实通知，或用示例体验完整流程。','<button class="button primary" data-demo>加载示例数据</button>')}</section><section class="panel"><div class="panel-head"><div class="panel-title"><h2>消息里的新变化</h2><small>${s.pending_reviews}</small></div><button class="text-button" data-view="inbox">查看收件箱 ↗</button></div>${preview||empty('还没有待确认消息','新通知、延期和材料变更会出现在这里。')}${state.proposals.length?'<p class="helper">核对后才写入任务，每次变更保留历史。</p>':''}</section></div>
    <div class="bottom-note"><span class="note-icon">✧</span><p><strong>让工具少打扰，让学习更专注。</strong><br>支持截图识别、通知来源核对、日历导出；Android 通知可通过手机伴侣补传。</p><button class="button subtle" data-view="mobile">连接手机 ↗</button></div><div class="toolbar"><button class="text-button notification-button" data-notifications>开启浏览器截止提醒</button><span class="helper">页面打开期间提醒；关闭页面后可用导出的日历提醒。</span>${state.tasks.length?'<button class="text-button" data-demo>加载示例数据</button>':''}</div>`;
}
function filteredTasks(){return state.tasks.filter(t=>(!filters.course||t.course===filters.course)&&(!filters.search||(t.title+t.course+t.scope).toLowerCase().includes(filters.search.toLowerCase()))&&(filters.status==='all'||filters.status==='active'&&!['submitted','cancelled'].includes(t.status)||t.status===filters.status))}
function taskRows(){
  const tasks=filteredTasks();
  $('#taskRows').innerHTML=tasks.length?tasks.map(t=>{const due=dueLabel(t);return `<article class="task-row"><span class="course-icon">${esc((t.course||'任务').slice(0,2))}</span><div class="task-body"><h3>${esc(t.title)}</h3><p><span>${esc(t.course||'课程待填写')}</span> · ${esc(t.scope||'未设置班级')} · ${esc(kindNames[t.kind])} ${t.sample?'· 示例':''}</p></div><div class="task-due">${pill(due.text,due.color)}<p>${esc(formatDeadline(t.deadline))}</p></div><select class="task-status" data-status="${t.id}" aria-label="${esc(t.title)}状态">${taskOptions(t.status)}</select><button class="button small" data-detail="${t.id}">查看详情</button></article>`}).join(''):empty('没有符合条件的任务','修改筛选条件，或先从消息收件箱确认任务。');
}
function renderTasks(){
  const courses=[...new Set(state.tasks.map(t=>t.course).filter(Boolean))].sort();
  content.innerHTML=intro('所有任务，都有清晰的去向。','按截止时间整理；完成和提交分别记录。','TASKS & CHECKLISTS')+`<div class="toolbar"><input id="taskSearch" aria-label="搜索任务" placeholder="搜索任务、课程或班级…" value="${esc(filters.search)}"><select id="courseFilter" aria-label="课程筛选"><option value="">全部课程</option>${courses.map(c=>`<option ${c===filters.course?'selected':''} value="${esc(c)}">${esc(c)}</option>`).join('')}</select><select id="statusFilter" aria-label="状态筛选"><option value="active" ${filters.status==='active'?'selected':''}>尚未提交</option><option value="all" ${filters.status==='all'?'selected':''}>全部任务</option>${Object.entries(statusNames).map(([k,v])=>`<option value="${k}" ${filters.status===k?'selected':''}>${v}</option>`).join('')}</select></div><section class="task-list" id="taskRows"></section><p class="helper">“已提交”是你的手动确认；本工具不会代交作业，也不推断原平台状态。</p>`;
  taskRows();
  $('#taskSearch').addEventListener('input',e=>{filters.search=e.target.value;taskRows()});
  $('#courseFilter').addEventListener('change',e=>{filters.course=e.target.value;taskRows()});
  $('#statusFilter').addEventListener('change',e=>{filters.status=e.target.value;taskRows()});
}
function proposalCard(p){
  const c=p.candidate,label={create:'新任务',update:'截止 / 材料变更',link:'重复任务 · 关联来源',cancel:'取消任务'}[p.action];
  const locked=p.target_id?'disabled':'';
  const precision=c.date_precision==='minute'?'minute':c.date_precision==='date'?'date':'unknown';
  return `<article class="proposal-card" data-proposal="${p.id}"><div class="proposal-heading"><div>${pill(c.operation==='update'?'延期 · 待确认':label,p.action==='cancel'?'red':p.action==='update'?'green':'amber')}${c.matchable?'':pill('名称需核对','outline')}${state.messages.find(m=>m.id===p.message_id)?.sample?pill('示例','outline'):''}<h3>${esc(c.course||'未识别课程')} · ${esc(c.title)}</h3><p class="source-line">${esc(state.messages.find(m=>m.id===p.message_id)?.source||'原始通知')} · ${esc(dateLabel(c.captured_at))}</p></div><span class="date-dot">REVIEW FIRST</span></div>
  ${p.before?`<div class="change-box"><span>当前任务</span><span class="old">${esc(formatDeadline(p.before.deadline))}</span><span>→</span><strong>${esc(p.action==='cancel'?'确认后取消':formatDeadline(c.deadline||p.before.deadline))}</strong></div>`:''}
  <div class="proposal-grid"><label class="field">任务名称<input data-field="title" value="${esc(c.title)}" maxlength="160" ${locked}></label><label class="field">课程<input data-field="course" value="${esc(c.course)}" maxlength="100" ${locked}></label><label class="field">班级 / 分组<input data-field="scope" value="${esc(c.scope)}" maxlength="100" ${locked}></label><label class="field deadline-field">截止时间（北京时间）<div class="deadline-control"><select data-precision><option value="unknown" ${precision==='unknown'?'selected':''}>未明确</option><option value="date" ${precision==='date'?'selected':''}>日期</option><option value="minute" ${precision==='minute'?'selected':''}>时刻</option></select><input data-field="deadline" type="${precision==='minute'?'datetime-local':'date'}" value="${c.deadline?esc(precision==='minute'?c.deadline.slice(0,16):c.deadline.slice(0,10)):''}" ${precision==='unknown'?'disabled':''}></div></label><label class="field">类型<select data-field="kind">${Object.entries(kindNames).map(([k,v])=>`<option value="${k}" ${c.kind===k?'selected':''}>${v}</option>`).join('')}</select></label></div>
  <label class="field">提交材料（每行一项）<textarea data-field="requirements" rows="2">${esc(c.requirements.join('\n'))}</textarea></label>
  ${c.warnings.length?`<div class="warning">${c.warnings.map(w=>`<p>△ ${esc(w)}</p>`).join('')}</div>`:''}
  <details class="evidence"><summary>查看消息原文与提取依据</summary><pre>${esc(state.messages.find(m=>m.id===p.message_id)?.text||c.evidence)}</pre><p>原文日期依据：${esc(c.deadline_evidence||'未识别')}。${p.target_id?'已有任务的名称、课程和班级不能在此更改；需重新导入以重新匹配。':''}</p></details><p class="error-text proposal-error" role="alert"></p>
  <div class="proposal-actions"><button class="button subtle" data-dismiss="${p.id}">忽略草稿</button><button class="button primary" data-confirm="${p.id}">${{create:'确认创建',update:'确认变更',link:'关联来源',cancel:'确认取消'}[p.action]}</button></div></article>`;
}
function renderInbox(){
  content.innerHTML=intro('每一条通知，都有据可查。','先核对，再创建任务。重复、延期和取消都会保留来源。','MESSAGE INBOX')+`<div class="section-tabs"><button class="section-tab ${inboxTab==='pending'?'active':''}" data-inbox-tab="pending">待确认草稿 ${state.proposals.length}</button><button class="section-tab ${inboxTab==='messages'?'active':''}" data-inbox-tab="messages">消息记录 ${state.messages.length}</button></div>`+
    (inboxTab==='pending'?(state.proposals.length?state.proposals.map(proposalCard).join(''):empty('待确认区已经清空','新通知进入这里，确认后会出现在待办中。','<button class="button primary" data-open-import>导入通知</button>')):(state.messages.length?state.messages.map(m=>`<article class="message-card"><div class="message-heading"><strong>${esc(m.source)}</strong><span>${esc(dateLabel(m.captured_at))}</span></div><div class="priority-meta">${pill(m.scope||'未设置班级','outline')}${pill(m.mode==='agent'?'模型工具提取':'本地规则提取','green')}${m.sample?pill('示例','amber'):''}</div><pre>${esc(m.text)}</pre>${m.trace.length?traceHTML(m.trace):''}</article>`).join(''):empty('还没有导入消息','文本、截图和手机通知都可以进入收件箱。')));
}
function renderCalendar(){
  const year=month.getFullYear(),mn=month.getMonth();
  const start=new Date(year,mn,1),offset=(start.getDay()+6)%7;
  const total=Math.ceil((new Date(year,mn+1,0).getDate()+offset)/7)*7;
  const today=cnLocalTime().slice(0,10),cells=[];
  for(let i=0;i<total;i++){
    const d=new Date(year,mn,1-offset+i);const stamp=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    const tasks=state.tasks.filter(t=>t.deadline?.slice(0,10)===stamp&&t.status!=='cancelled');
    cells.push(`<div class="day ${stamp===today?'today':''} ${d.getMonth()!==mn?'other-month':''}"><span class="day-number">${d.getDate()}</span>${tasks.map(t=>`<button class="calendar-task ${t.status==='submitted'?'submitted':''}" data-detail="${t.id}" title="${esc(t.course+' · '+t.title+' / '+formatDeadline(t.deadline))}">${esc(t.course+' · '+t.title)}</button>`).join('')}</div>`);
  }
  content.innerHTML=intro('给每个截止日期，留好位置。','统一查看课程任务，导出到你常用的手机或电脑日历。','DEADLINE CALENDAR')+`<div class="calendar-toolbar"><div class="calendar-controls"><button class="button small" data-month="-1" aria-label="上个月">‹</button><h2>${year} 年 ${mn+1} 月</h2><button class="button small" data-month="1" aria-label="下个月">›</button><button class="text-button" data-month="0">本月</button></div><button id="exportCalendar" class="button primary" data-download="calendar">↓ 导出日历 .ics</button></div><section class="calendar">${['周一','周二','周三','周四','周五','周六','周日'].map(d=>`<div class="weekday">${d}</div>`).join('')}${cells.join('')}</section><p class="calendar-help">精确时刻的任务附带提前 2 小时提醒；日期未写明时刻的任务按全天事件导出。导出文件是当前快照，变更后需要重新导入日历。</p>`;
}
async function renderMobile(){
  content.innerHTML=intro('连接手机，收好每一次通知。','Android 通知进入本地收件箱，任务确认仍由你掌握。','MOBILE CONNECTION')+'<div class="loading">正在读取连接配置…</div>';
  try{
    settings=await json('/api/settings');
    if(view!=='mobile')return;
    const lan=settings.addresses.find(a=>/^192\.168\.|^10\.|^172\.(1[6-9]|2\d|3[01])\./.test(a));
    content.innerHTML=intro('连接手机，收好每一次通知。','Android 通知进入本地收件箱，任务确认仍由你掌握。','MOBILE CONNECTION')+`<section class="mobile-intro"><span class="eyebrow">ANDROID COMPANION</span><h2>让手机通知进入收件箱</h2><p>通过用户授权的通知访问读取标题与正文；电脑不在线时在手机排队。它能接收系统已送达的通知，完整任务详情仍需核对原平台。</p></section><div class="two-columns"><section class="panel connect-panel"><div class="panel-head"><h2>配对信息</h2><span class="connection-state">${settings.listen_host==='0.0.0.0'?'已开启局域网监听':'当前仅本机监听'}</span></div><label class="field">手机填写的服务地址<input class="pair-input" readonly value="${esc('http://'+(lan||'你的电脑局域网IP')+':'+settings.server_port)}"></label><p class="helper">先结束本机启动窗口，再运行项目中的 start-lan.cmd；手机和电脑需处于可互通网络。</p><label class="field">访问令牌<div class="pair-row"><input id="pairToken" class="pair-input" type="password" readonly placeholder="点击显示后复制到手机"><button id="tokenReveal" class="button small">显示配对令牌</button><button id="tokenCopy" class="button small">复制</button></div></label><p class="helper">令牌只分享给自己的设备。局域网 HTTP 适用于可信网络；远程部署使用 HTTPS。</p><label class="field">允许接收的应用包名<textarea id="packageList" rows="4">${esc(settings.allowed_packages.join('\n'))}</textarea><span class="helper">每行一个完整包名；手机端也需设置相同白名单。</span></label><button id="savePackages" class="button primary">保存白名单</button></section><section class="panel"><div class="panel-head"><h2>首次连接</h2></div><ol class="step-list"><li>在 Android Studio 打开 <code>android/</code> 工程，构建并安装手机伴侣。</li><li>在手机填写服务地址、令牌、班级和应用白名单。</li><li>点击“授权通知访问”，在系统设置中启用 CourseInbox。</li><li>接收一条真实课程通知，或发送客户端内的示例事件。</li><li>在这里刷新，进入消息收件箱核对草稿。</li></ol><div class="model-notice">手机工程尚需在实体设备构建、授权和验证；当前电脑端接收接口已用模拟 Android 事件验收。<br>iPhone 可使用截图或文字导入。普通应用不能全局监听其他应用通知。</div><button class="text-button" data-view="inbox">查看收到的消息 ↗</button><div class="model-notice"><strong>可选模型配置</strong><br>在启动窗口设置 <code>CI_MODEL_PROVIDER=ollama</code>、<code>CI_MODEL</code>，重启后即可使用支持工具调用的本地模型。兼容接口、环境变量和安装步骤见 README。当前模式：${esc(state.agent.mode==='agent'?'模型工具调用':'本地规则提取')}。</div></section></div><div class="bottom-note"><p>浏览器截止提醒需要页面保持打开；通知采集依赖 Android 通知访问权限和来源应用实际发出通知。客户端启动或收到新通知时尝试补传。</p><button class="button subtle" data-download="backup">导出数据备份</button></div>`;
  }catch(error){toast(error.message,true)}
}
function renderView(){
  document.querySelectorAll('.sidebar [data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  ({today:renderToday,tasks:renderTasks,inbox:renderInbox,calendar:renderCalendar,mobile:renderMobile}[view]||renderToday)();
}
function showView(next){
  if(!['today','tasks','inbox','calendar','mobile'].includes(next))return;
  view=next;history.replaceState(null,'','#'+next);renderView();window.scrollTo({top:0});
}
async function saveDetail(changes){
  const id=detailId;
  document.querySelectorAll('#taskDetail input,#taskDetail select').forEach(i=>i.disabled=true);
  try{
    await json('/api/tasks/'+id,{method:'PATCH',body:{...changes,expected_version:Number($('#taskDetail').dataset.version)}});
    await refresh();
    if($('#taskDialog').open && detailId===id)await openTask(id);
  }catch(error){
    toast(error.message,true);
    if($('#taskDialog').open && detailId===id)await openTask(id);
  }finally{document.querySelectorAll('#taskDetail input,#taskDetail select').forEach(i=>i.disabled=false)}
}
async function openTask(id){
  detailId=id;
  const task=await json('/api/tasks/'+id);
  if(detailId!==id)return;
  $('#detailTitle').textContent=task.title;
  $('#taskDetail').innerHTML=`<div class="detail-meta">${pill(task.course||'课程未填写','green')}${pill(task.scope||'未设置班级','outline')}${pill(kindNames[task.kind])}${task.sample?pill('示例','amber'):''}</div><p class="due-meta">截止：${esc(formatDeadline(task.deadline))}</p><label class="field">任务状态<select id="detailStatus" data-detail-status="${task.id}">${taskOptions(task.status)}</select></label>${task.status==='done'?'<p class="detail-status-note">已做完，记得在原平台提交</p>':'<p class="helper">状态由你手动记录；“已提交”不代表原平台回执。</p>'}<h3>提交材料</h3><div class="checklist">${task.checklist.length?task.checklist.map((x,i)=>`<label><input type="checkbox" data-check="${i}" ${x.done?'checked':''}>${esc(x.text)}</label>`).join(''):'<p class="helper">原文未提取到提交材料。</p>'}</div><details class="evidence"><summary>消息来源（${task.sources.length}）</summary>${task.sources.map(m=>`<p>${esc(m.source)} · ${esc(dateLabel(m.captured_at))}</p><pre>${esc(m.text)}</pre>`).join('')}</details><details class="evidence"><summary>变更历史（${task.history.length}）</summary>${task.history.map(h=>`<div class="detail-history"><strong>${esc(dateLabel(h.at))} · ${esc({create:'创建任务',update:'确认变更',link:'关联来源',cancel:'取消任务','status/checklist':'状态或材料更新'}[h.action]||h.action)}</strong>${esc(h.before?formatDeadline(h.before.deadline)+' → '+formatDeadline(h.after.deadline):formatDeadline(h.after.deadline))}<br>状态：${esc(statusNames[h.after.status])}</div>`).join('')}</details>`;
  $('#taskDetail').dataset.version=task.version;
  if(!$('#taskDialog').open)$('#taskDialog').showModal();
}
function openImport(){
  $('#noticeTime').value=cnLocalTime();$('#noticeMode').value=state.agent.mode==='agent'?'agent':'rules';$('#importError').textContent='';
  $('#importDialog').showModal();
}
function traceHTML(trace){return `<details class="trace-panel"><summary>工具执行轨迹 · ${trace.length} 次调用</summary>${trace.map((t,i)=>`<p>${i+1}. ${esc(t.tool)}</p><pre>${esc(JSON.stringify(t.result,null,2).slice(0,6000))}</pre>`).join('')}</details>`}
async function download(which){
  const response=await api(which==='calendar'?'/api/calendar.ics':'/api/export.json');
  const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=which==='calendar'?'courseinbox.ics':'courseinbox-backup.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);
}
async function notify(summary){
  if(!('Notification' in window)||Notification.permission!=='granted'||localStorage.getItem('courseinbox-reminders')!=='enabled')return;
  for(const r of summary.reminders){
    const key='courseinbox-notified:'+r.task_id+':'+r.deadline+':'+r.level;
    if(localStorage.getItem(key))continue;
    new Notification(r.overdue?'课程任务已逾期':'课程任务即将截止',{body:r.course+' · '+r.title+'\n'+formatDeadline(r.deadline),tag:r.task_id,icon:'/favicon.svg'});
    localStorage.setItem(key,new Date().toISOString());
  }
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  try{
    if(button.hasAttribute('data-close')){button.closest('dialog').close();return}
    if(button.dataset.view){showView(button.dataset.view);return}
    if(button.dataset.inboxTab){inboxTab=button.dataset.inboxTab;renderInbox();return}
    if(button.id==='importOpen'||button.hasAttribute('data-open-import')){openImport();return}
    if(button.id==='refreshButton'){await busy(button,()=>refresh());toast('数据已刷新');return}
    if(button.hasAttribute('data-demo')){await busy(button,async()=>{await json('/api/demo',{method:'POST',body:{}});await refresh();toast('示例数据已加载，全部标注为示例')});return}
    if(button.dataset.detail){await openTask(button.dataset.detail);return}
    if(button.dataset.confirm){
      const action=state.proposals.find(p=>p.id===button.dataset.confirm)?.action;
      const card=button.closest('.proposal-card');$('.proposal-error',card).textContent='';
      const fields={};for(const name of ['title','course','scope','kind'])fields[name]=$(`[data-field="${name}"]`,card).value;
      const precision=$('[data-precision]',card).value,deadline=$('[data-field="deadline"]',card).value;
      if(precision!=='unknown'&&!deadline)throw new Error('请填写截止日期，或选择“未明确”。');
      fields.deadline=precision==='unknown'?null:precision==='minute'?deadline+(deadline.length===16?':00':'')+'+08:00':deadline;
      fields.requirements=$('[data-field="requirements"]',card).value.split('\n').map(x=>x.trim()).filter(Boolean);
      await busy(button,async()=>{try{await json('/api/proposals/'+button.dataset.confirm+'/confirm',{method:'POST',body:fields});await refresh();toast(action==='update'?'变更已确认':'任务已确认')}catch(error){$('.proposal-error',card).textContent=error.message;throw error}});return;
    }
    if(button.dataset.dismiss){await busy(button,async()=>{await json('/api/proposals/'+button.dataset.dismiss+'/dismiss',{method:'POST',body:{}});await refresh();toast('草稿已忽略，消息原文仍保留')});return}
    if(button.hasAttribute('data-month')){month=button.dataset.month==='0'?new Date():new Date(month.getFullYear(),month.getMonth()+Number(button.dataset.month),1);renderCalendar();return}
    if(button.dataset.download){await busy(button,()=>download(button.dataset.download));return}
    if(button.id==='tokenReveal'){const input=$('#pairToken');input.value=token;input.type=input.type==='password'?'text':'password';button.textContent=input.type==='text'?'隐藏令牌':'显示配对令牌';return}
    if(button.id==='tokenCopy'){await navigator.clipboard.writeText(token);toast('配对令牌已复制');return}
    if(button.id==='savePackages'){await busy(button,async()=>{await json('/api/settings',{method:'POST',body:{allowed_packages:$('#packageList').value.split('\n').map(x=>x.trim()).filter(Boolean)}});toast('应用白名单已保存')});return}
    if(button.id==='assistantOpen'){$('#assistantMode').textContent=state.agent.mode==='agent'?'模型通过工具查询；不会直接修改任务。':'本地规则查询；自由问答需配置模型。';$('#assistantDialog').showModal();return}
    if(button.hasAttribute('data-notifications')){if(!('Notification' in window))throw new Error('此浏览器暂不支持系统通知。');const permission=await Notification.requestPermission();if(permission==='granted'){localStorage.setItem('courseinbox-reminders','enabled');await notify(state.summary);toast('已开启页面运行期间的截止提醒')}else{toast('系统通知未授权，页面内仍显示截止提醒',true)}return}
  }catch(error){toast(error.message,true)}
});
document.addEventListener('change',async event=>{
  const input=event.target;
  try{
    if(input.hasAttribute('data-precision')){const field=$('[data-field="deadline"]',input.closest('.proposal-card'));field.disabled=input.value==='unknown';field.type=input.value==='minute'?'datetime-local':'date';field.value='';return}
    if(input.dataset.status){const task=state.tasks.find(t=>t.id===input.dataset.status);await json('/api/tasks/'+task.id,{method:'PATCH',body:{status:input.value,expected_version:task.version}});await refresh();toast(input.value==='done'?'已做完，记得在原平台提交':'任务状态已保存');return}
    if(input.dataset.detailStatus){await saveDetail({status:input.value});return}
    if(input.hasAttribute('data-check')){const values=Array.from($('#taskDetail').querySelectorAll('[data-check]')).map(i=>i.checked);await saveDetail({checklist:values});return}
  }catch(error){toast(error.message,true);if(detailId&&$('#taskDialog').open)await openTask(detailId);else await refresh()}
});
$('#noticeFile').addEventListener('change',async event=>{
  const file=event.target.files[0];if(!file)return;
  const status=$('#fileStatus');status.textContent='正在本地识别文件…';$('#importSubmit').disabled=true;
  try{
    if(file.size>8*1024*1024)throw new Error('文件超过 8 MB，请缩小后再导入。');
    const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('文件读取失败'));reader.readAsDataURL(file)});
    const result=await json('/api/files/extract',{method:'POST',body:{filename:file.name,content_base64:data}});
    $('#noticeText').value=result.text;status.textContent=(result.engine.startsWith('windows-ocr')?'Windows 中文 OCR':result.engine)+' · 已提取，请检查识别文字后生成草稿。';
  }catch(error){status.textContent=error.message;toast(error.message,true)}finally{$('#importSubmit').disabled=false}
});
$('#importForm').addEventListener('submit',async event=>{
  event.preventDefault();$('#importError').textContent='';
  await busy($('#importSubmit'),async()=>{
    try{
      const result=await json('/api/messages',{method:'POST',body:{text:$('#noticeText').value,source:$('#noticeSource').value,course:$('#noticeCourse').value,scope:$('#noticeScope').value,captured_at:$('#noticeTime').value+':00+08:00',mode:$('#noticeMode').value}});
      $('#importDialog').close();inboxTab='pending';view='inbox';await refresh();showView('inbox');
      $('#noticeText').value='';$('#noticeFile').value='';$('#fileStatus').textContent='';
      toast(result.duplicate?'重复消息已关联，未重复创建':result.proposals.length?`已生成 ${result.proposals.length} 条待确认草稿`:'消息已保存，没有识别到学习任务');
    }catch(error){$('#importError').textContent=error.message}
  });
});
$('#assistantForm').addEventListener('submit',async event=>{
  event.preventDefault();await busy($('#assistantSubmit'),async()=>{
    $('#assistantAnswer').hidden=false;$('#assistantAnswer').textContent='正在查询任务…';$('#assistantTrace').innerHTML='';
    try{const scope=$('#assistantScope').value.trim();const result=await json('/api/assistant',{method:'POST',body:{question:$('#assistantQuestion').value,course:$('#assistantCourse').value.trim(),scope:scope||null}});$('#assistantAnswer').textContent=result.answer;$('#assistantTrace').innerHTML=traceHTML(result.trace)}catch(error){$('#assistantAnswer').textContent=error.message}
  });
});
$('#authForm').addEventListener('submit',async event=>{
  event.preventDefault();token=$('#authToken').value.trim();try{await refresh();sessionStorage.setItem('courseinbox-token',token);$('#authDialog').close()}catch(error){$('#authError').textContent=error.message}
});
$('#authDialog').addEventListener('cancel',e=>e.preventDefault());
async function boot(){
  content.innerHTML='<div class="loading">正在打开你的学习空间…</div>';
  try{const response=await fetch('/api/bootstrap');if(response.ok)token=(await response.json()).token;else token=sessionStorage.getItem('courseinbox-token')||'';await refresh(false);view=location.hash.slice(1)||'today';if(!['today','tasks','inbox','calendar','mobile'].includes(view))view='today';renderView()}catch(error){content.innerHTML=empty('连接尚未完成','输入电脑端的访问令牌后可打开学习空间。');$('#authDialog').showModal()}
}
setInterval(async()=>{
  if(!token)return;
  try{const summary=await json('/api/dashboard');await notify(summary);if(!document.querySelector('dialog[open]')&&!document.activeElement?.matches('input,textarea,select')&&view!=='inbox'&&view!=='mobile')await refresh()}catch{$('.sync-label').textContent='连接已断开'}
},15000);
boot();
