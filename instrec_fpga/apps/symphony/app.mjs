import { GROUPS, CLASS8, normalizeSession, deriveSegments, querySegments, parseTelemetry, createDemoSession, exportSegmentsCSV, exportSessionJSON, formatTime } from './model.mjs';

const $ = (id) => document.getElementById(id);
const escapeHTML = (text) => String(text ?? '').replace(/[&<>"']/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char]));
const byGroup = (id) => GROUPS.find((group) => group.id === id);
const clock = (time) => formatTime(Math.max(0, Number.isFinite(time) ? time : 0)).replace(/\.0$/, '');
const uid = () => `note-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.floor(Math.random()*1000000)}`}`;
const STORAGE_KEY = 'symphony-studio-v1';
const state = { session:createDemoSession(), sessions:[], segments:[], view:'guide', time:21.5, playing:false, focus:null, groups:[], annotationGroups:[], editing:null, selected:null, loop:false, audioURL:null, audioSession:null, telemetry:null, serialConnected:false, after:0, reference:null };
const audio = $('audio');
let lastAnimationTime = null;
let lastDrawTime = 0;
let toastTimer;
let saveWarningShown = false;

function toast(message) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(() => { $('toast').hidden=true; },3800); }
function sourceName(session=state.session) { if(session.source.kind==='inference')return session.source.uri?.endsWith('reference_vectors.npz')?'模型参考':'识别结果';return ({demo:'交互演示',manual:'本地音乐',import:'导入结果'})[session.source.kind] ?? '导入结果'; }
function persist() {
  try {
    const key=state.session.track.id;
    state.sessions=state.sessions.filter((session) => session.track.id!==key);
    state.sessions.unshift(state.session);
    state.sessions=state.sessions.slice(0,8);
    const data=JSON.stringify({version:1,current:key,sessions:state.sessions});
    if(data.length>5*1024*1024) throw new Error('会话已超出浏览器存储预算');
    localStorage.setItem(STORAGE_KEY,data);
  } catch { if(!saveWarningShown){ toast('本机存储空间不足，请使用“保存会话 JSON”备份。'); saveWarningShown=true; } }
  renderSessionPicker();
}
function restore() {
  try {
    const raw=localStorage.getItem(STORAGE_KEY); if(!raw)return;
    if(raw.length>5*1024*1024)throw new Error('会话过大');
    const parsed=JSON.parse(raw); if(parsed.version!==1 || !Array.isArray(parsed.sessions) || parsed.sessions.length>8)throw new Error('会话格式变化');
    state.sessions=parsed.sessions.map(normalizeSession);
    state.session=state.sessions.find((session) => session.track.id===parsed.current) ?? state.sessions[0] ?? state.session;
    state.time=Math.min(state.time,state.session.track.duration);
  } catch { toast('已打开演示；上次会话格式有误，可重新导入 JSON。'); }
}
function renderSessionPicker() {
  $('session-select').replaceChildren(...state.sessions.map((session) => { const option=document.createElement('option'); option.value=session.track.id; option.textContent=session.track.title; option.selected=session.track.id===state.session.track.id; return option; }));
}
function setSession(raw,{time=0,keepAudio=false}={}) {
  const next=normalizeSession(raw);
  pause();
  if(!keepAudio && state.audioSession!==next.track.id) {
    audio.removeAttribute('src'); audio.load(); state.audioSession=null;
    if(state.audioURL) URL.revokeObjectURL(state.audioURL); state.audioURL=null;
  }
  state.session=next; state.time=Math.min(time,next.track.duration); state.focus=null; state.groups=[]; state.selected=null; state.loop=false;
  $('loop-toggle').setAttribute('aria-pressed','false');
  state.segments=deriveSegments(next.frames);
  persist(); renderAll();
}
function showView(view) {
  state.view=view; $('guide-view').hidden=view!=='guide'; $('library-view').hidden=view!=='library';
  for(const [id,name] of [['nav-guide','guide'],['nav-library','library']]){ $(id).classList.toggle('active',view===name); if(view===name)$(id).setAttribute('aria-current','page'); else $(id).removeAttribute('aria-current'); }
  $('breadcrumb-current').textContent=view==='guide'?'交响导赏':'片段与标注'; location.hash=view;
  if(view==='library')renderLibrary();
}
function currentFrame() { const frame=state.session.frames.findLast((item) => item.start<=state.time); return frame && state.time<frame.end ? frame : null; }
function currentGroups() { return GROUPS.filter((group) => state.segments.some((segment) => segment.group===group.id && segment.start<=state.time && state.time<segment.end)); }
function dominantGroup(frame) { if(!frame)return null; const scores=frame.dominance.map((score,index) => frame.activity[index]>.5?score:0); const top=Math.max(...scores); return top>0?GROUPS[scores.indexOf(top)]:null; }

function stageSVG() {
  const zones=[
    ['percussion','M142 77 Q260 5 378 77 L356 109 Q260 56 164 109 Z',260,63],
    ['brass','M164 118 Q260 65 356 118 L337 149 Q260 108 183 149 Z',260,115],
    ['woodwinds','M185 156 Q260 113 335 156 L317 186 Q260 151 203 186 Z',260,158],
    ['strings','M73 111 Q112 95 153 110 L198 192 Q224 207 247 211 L247 243 Q133 237 73 159 Z',151,183],
    ['keys','M367 109 Q405 95 447 111 L447 159 Q387 237 273 243 L273 211 Q297 207 322 192 Z',366,183],
  ];
  return `<svg viewBox="0 0 520 265" role="img" aria-label="交响乐队声部分区示意"><path d="M48 145 Q260 -52 472 145" fill="none" stroke="#edf0e7" stroke-dasharray="3 5"/><path d="M55 164 Q260 294 465 164" fill="none" stroke="#edf0e7"/>${zones.map(([id,path,x,y])=>{const group=byGroup(id);const seats=Array.from({length:5},(_,i)=>`<circle class="seat" cx="${x+(i-2)*14}" cy="${y-20}" r="2.4"/>`).join('');return `<g role="button" tabindex="0" aria-label="聚焦${escapeHTML(group.nameZh)}" aria-pressed="false" class="stage-zone" data-stage-group="${id}" style="--group-color:${group.color}"><path class="zone-fill" d="${path}"/>${seats}<text x="${x}" y="${y+3}" text-anchor="middle">${escapeHTML(group.nameZh)}</text><text class="zone-count" x="${x}" y="${y+17}" text-anchor="middle" data-stage-score="${id}">—</text></g>`;}).join('')}<circle cx="260" cy="229" r="5" fill="#536b4d"/><path d="M254 244q6-9 12 0M253 224l-7-6m20 6 9-6" fill="none" stroke="#536b4d" stroke-width="1.6"/><text x="260" y="261" text-anchor="middle" font-size="8" fill="#a4ad98" letter-spacing="2">CONDUCTOR</text></svg>`;
}
function buildComponents() {
  $('orchestra-stage').innerHTML=stageSVG();
  $('activity-bars').innerHTML=GROUPS.map((group,index)=>`<div class="activity-row" style="--group-color:${group.color}"><span class="group-emblem" aria-hidden="true">${['♬','♮','♩','♧','♭'][index]}</span><div><div class="group-label"><span>${escapeHTML(group.nameZh)}</span><small>${group.id.toUpperCase()}</small></div><div class="meter" role="meter" aria-label="${escapeHTML(group.nameZh)}活跃度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" id="meter-${group.id}"><span id="bar-${group.id}" style="width:0"></span></div></div><span class="score" id="score-${group.id}">—</span></div>`).join('');
  for(const container of ['group-filters','annotation-groups']){
    $(container).innerHTML=GROUPS.map((group)=>`<button type="button" class="group-chip" style="--group-color:${group.color}" data-${container==='group-filters'?'filter':'annotation'}-group="${group.id}" aria-pressed="false">${escapeHTML(group.nameZh)}</button>`).join('');
  }
  document.querySelectorAll('[data-stage-group]').forEach((element)=>{
    const focus=()=>{state.focus=state.focus===element.dataset.stageGroup?null:element.dataset.stageGroup; renderTimeline(); renderCurrent();};
    element.addEventListener('click',focus); element.addEventListener('keydown',(event)=>{if(['Enter',' '].includes(event.key)){event.preventDefault();focus();}});
  });
  document.querySelectorAll('[data-filter-group]').forEach((button)=>button.addEventListener('click',()=>{const id=button.dataset.filterGroup; state.groups=state.groups.includes(id)?state.groups.filter((item)=>item!==id):[...state.groups,id]; renderLibrary();}));
  document.querySelectorAll('[data-annotation-group]').forEach((button)=>button.addEventListener('click',()=>{const id=button.dataset.annotationGroup; state.annotationGroups=state.annotationGroups.includes(id)?state.annotationGroups.filter((item)=>item!==id):[...state.annotationGroups,id]; renderAnnotationGroups();}));
}
function renderTimeline() {
  const duration=state.session.track.duration;
  const scale=Array.from({length:6},(_,index)=>`<span>${clock(duration*index/5)}</span>`).join('');
  const rows=GROUPS.map((group)=>{
    const blocks=state.segments.filter((segment)=>segment.group===group.id).map((segment)=>`<button class="timeline-block" style="left:${segment.start/duration*100}%;width:${segment.duration/duration*100}%;--group-color:${group.color}" data-segment-id="${escapeHTML(segment.id)}" aria-label="${escapeHTML(group.nameZh)} ${clock(segment.start)} 至 ${clock(segment.end)}" title="${escapeHTML(group.nameZh)} · ${clock(segment.start)}—${clock(segment.end)}"></button>`).join('');
    return `<div class="timeline-row${state.focus && state.focus!==group.id?' dimmed':''}"><span class="row-name">${escapeHTML(group.nameZh)}</span><div class="timeline-track">${blocks}</div></div>`;
  }).join('');
  const notes=state.session.annotations.map((note)=>`<button class="timeline-block manual" style="left:${note.start/duration*100}%;width:${(note.end-note.start)/duration*100}%" data-note-id="${escapeHTML(note.id)}" aria-label="编辑标注：${escapeHTML(note.label)}" title="${escapeHTML(note.label)}"></button>`).join('');
  $('timeline').innerHTML=`<div class="timeline-scale">${scale}</div>${rows}<div class="timeline-row"><span class="row-name">我的标注</span><div class="timeline-track">${notes}</div></div><div class="timeline-cursor" style="--progress:${state.time/duration}"></div>`;
  $('timeline').querySelectorAll('[data-segment-id]').forEach((button)=>button.addEventListener('click',()=>{const segment=state.segments.find((item)=>item.id===button.dataset.segmentId); selectSegment(segment,false);}));
  $('timeline').querySelectorAll('[data-note-id]').forEach((button)=>button.addEventListener('click',()=>editAnnotation(state.session.annotations.find((note)=>note.id===button.dataset.noteId))));
}
function renderCurrent() {
  const frame=currentFrame(); const active=currentGroups(); const dominant=dominantGroup(frame);
  $('active-count').textContent=frame?`${active.length} 个乐器组活跃`:'等待窗口结果';
  $('dominant-name').textContent=dominant?.nameZh ?? (frame?'无主导组':'等待结果');
  $('dominant-description').textContent=dominant?`${dominant.nameZh}在当前窗口中占据主导，留意它与其他声部的呼应。`:(frame?'这段音乐暂时收束，等待下一个声部进入。':'载入对应的五组结果后，这里会显示主导变化。');
  $('clear-focus').hidden=!state.focus;
  for(const group of GROUPS){
    const score=frame?Math.round(frame.activity[group.index]*100):null;
    $(`score-${group.id}`).textContent=score===null?'—':`${score}%`;
    $(`bar-${group.id}`).style.width=`${score??0}%`;
    $(`meter-${group.id}`).setAttribute('aria-valuenow',String(score??0));
    const zone=document.querySelector(`[data-stage-group="${group.id}"]`);
    zone.classList.toggle('is-active',active.some((item)=>item.id===group.id));zone.classList.toggle('is-focus',state.focus===group.id);zone.setAttribute('aria-pressed',String(state.focus===group.id));
    document.querySelector(`[data-stage-score="${group.id}"]`).textContent=score===null?'待分析':`${score}%`;
  }
  const names=active.map((group)=>group.nameZh);
  $('listening-note').textContent=!frame?'音乐可以先听起来。载入识别结果后，声部的轨迹会在这里展开。':names.length===0?'音乐在此刻留白。听见停顿，也听见下一个声部进入前的呼吸。':names.length===1?`${names[0]}独自展开这一段。留意音色的质地，以及旋律的走向。`:`${names.join('、')}在这里相遇。${dominant?`${dominant.nameZh}走在前方，其余声部共同织起音乐的层次。`:'留意不同音色如何交织。'}`;
  const nearby=state.segments.flatMap((segment)=>[{...segment,eventTime:segment.start,event:'进入'},{...segment,eventTime:segment.end,event:'退出'}]).filter((event)=>event.eventTime<=state.time&&event.eventTime>=Math.max(0,state.time-18)).sort((a,b)=>b.eventTime-a.eventTime).slice(0,3);
  $('event-chips').innerHTML=nearby.map((event)=>`<button class="event-chip" data-event-time="${event.eventTime}">${clock(event.eventTime)} · ${escapeHTML(byGroup(event.group).nameZh)}${event.event}</button>`).join('');
  document.querySelectorAll('[data-event-time]').forEach((button)=>button.addEventListener('click',()=>seek(Number(button.dataset.eventTime))));
  const cursor=$('timeline').querySelector('.timeline-cursor');if(cursor)cursor.style.setProperty('--progress',String(state.time/state.session.track.duration));
  $('elapsed').textContent=clock(state.time); $('seek').value=String(state.time);
  $('play-toggle').textContent=state.playing?'Ⅱ':'▶'; $('play-toggle').setAttribute('aria-label',state.playing?'暂停':'播放');
}
function renderNotes() {
  const notes=[...state.session.annotations].sort((a,b)=>a.start-b.start).slice(0,2);
  $('recent-annotations').classList.toggle('empty-mini',!notes.length);
  $('recent-annotations').innerHTML=notes.length?notes.map((note)=>`<button class="mini-note" data-edit-note="${escapeHTML(note.id)}"><time>${clock(note.start)}</time><strong>${escapeHTML(note.label)}</strong><span>↗</span></button>`).join(''):'在喜欢的片段留下一个记号。';
  $('recent-annotations').querySelectorAll('[data-edit-note]').forEach((button)=>button.addEventListener('click',()=>editAnnotation(state.session.annotations.find((note)=>note.id===button.dataset.editNote))));
}
function renderAll() {
  const session=state.session;
  $('source-label').textContent=sourceName(); $('track-title').textContent=session.track.title; $('player-title').textContent=session.track.title; $('sidebar-title').textContent=session.track.title;
  $('session-kicker').textContent=`${sourceName()} · ${clock(session.track.duration)}`;
  $('track-subtitle').textContent=session.track.description ?? session.source.description ?? '按乐器组探索音乐，用标注留下你的聆听笔记。';
  $('sidebar-description').textContent=session.source.kind==='demo'?'人工构造的声部变化，供体验导赏与标注。':'当前会话的结果与标注保存在本机。';
  $('player-mode').textContent=state.audioSession===session.track.id?'本地音频 · 已关联':`${sourceName()} · 无音频`;
  $('activity-footnote').textContent=session.source.kind==='demo'?'演示分数用于体验交互；实际结果由导入数据提供。':'五个独立的模型分数，保留合奏中的每个声部。';
  $('seek').max=String(session.track.duration); $('duration').textContent=clock(session.track.duration);
  document.querySelectorAll('[data-filter-group]').forEach((button)=>button.setAttribute('aria-pressed',String(state.groups.includes(button.dataset.filterGroup))));
  renderTimeline();renderNotes();renderCurrent();renderLibrary();renderSessionPicker();
}
function allSegments() { return [...state.segments.map((item)=>({...item,kind:'auto'})),...state.session.annotations.map((item)=>({...item,duration:item.end-item.start,kind:'manual'}))]; }
function filteredSegments() {
  const source=$('segment-source').value;
  return querySegments(allSegments().filter((item)=>source==='all'||item.kind===source),{text:$('search-query').value,groups:state.groups,mode:$('search-mode').value,minDuration:Number($('minimum-duration').value),dominantOnly:$('dominant-only').checked});
}
function renderLibrary() {
  document.querySelectorAll('[data-filter-group]').forEach((button)=>button.setAttribute('aria-pressed',String(state.groups.includes(button.dataset.filterGroup))));
  let results=[];try{results=filteredSegments();}catch(error){toast(error.message);}
  $('result-count').textContent=`${results.length} 个片段`; $('result-context').textContent=state.session.track.title;
  $('result-list').replaceChildren();
  if(!results.length){$('result-list').innerHTML='<div class="empty-state"><h3>给音乐，多一种寻找方式。</h3><p>试着减少筛选条件，或为当前音乐添加第一条标注。</p><button class="secondary-button" id="empty-add">＋ 添加标注</button></div>'; $('empty-add').addEventListener('click',()=>editAnnotation());return;}
  const fragment=document.createDocumentFragment();
  for(const result of results.slice(0,250)){
    const isManual=result.kind==='manual'; const row=document.createElement('article'); row.className='result-row';row.dataset.start=result.start;row.dataset.end=result.end;
    const title=isManual?result.label:result.groups.map((id)=>byGroup(id).nameZh).join(' · ')+(result.groups.length>1?'同时活跃':'活跃片段');
    row.innerHTML=`<button class="result-play" aria-label="播放片段 ${escapeHTML(title)}">▶</button><div class="result-main"><div class="result-title"><strong>${escapeHTML(title)}</strong><span class="result-type">${isManual?'人工标注':'自动识别'}</span><time class="result-time">${clock(result.start)} — ${clock(result.end)}</time></div>${result.notes&&isManual?`<p class="result-notes">${escapeHTML(result.notes)}</p>`:''}<div class="result-tags">${result.groups.map((id)=>`<span class="result-tag" style="--group-color:${byGroup(id).color}">${escapeHTML(byGroup(id).nameZh)}</span>`).join('')}${!result.groups.length?'<span class="result-tag">自由标注</span>':''}</div></div><div class="result-end"><span>${(result.end-result.start).toFixed(1)} 秒</span><button class="text-button">${isManual?'编辑':'标注此段'} ↗</button></div>`;
    row.querySelector('.result-play').addEventListener('click',()=>selectSegment(result,true));
    row.querySelector('.result-end button').addEventListener('click',()=>isManual?editAnnotation(state.session.annotations.find((item)=>item.id===result.id)):editAnnotation(null,result));fragment.append(row);
  }
  $('result-list').append(fragment);
  if(results.length>250){const more=document.createElement('p');more.className='microcopy';more.textContent=`当前显示前 250 个片段，共 ${results.length} 个。可缩小筛选范围；CSV 会导出全部匹配结果。`;$('result-list').append(more);}
}
function clearFilters(){state.groups=[];$('search-query').value='';$('search-mode').value='any';$('segment-source').value='all';$('minimum-duration').value='0';$('dominant-only').checked=false;renderLibrary();}
function seek(time){state.time=Math.min(state.session.track.duration,Math.max(0,time));if(state.audioSession===state.session.track.id&&Number.isFinite(audio.duration))audio.currentTime=Math.min(state.time,audio.duration);renderCurrent();}
function pause(){state.playing=false;audio.pause();lastAnimationTime=null;if($('play-toggle')){$('play-toggle').textContent='▶';$('play-toggle').setAttribute('aria-label','播放');}}
async function play(){
  if(state.time>=state.session.track.duration)seek(state.loop&&state.selected?state.selected.start:0);
  if(state.audioSession===state.session.track.id){try{audio.currentTime=state.time;await audio.play();}catch{toast('音频播放失败，请重新载入受支持的音频文件。');return;}}
  state.playing=true;lastAnimationTime=null;renderCurrent();
}
function selectSegment(segment,autoplay){state.selected=segment;seek(segment.start);if(autoplay){state.loop=true;$('loop-toggle').setAttribute('aria-pressed','true');play();}else toast(`${clock(segment.start)} — ${clock(segment.end)} · 可标注或循环试听`);}
function tick(now){
  if(state.playing){
    if(state.audioSession===state.session.track.id)state.time=audio.currentTime;
    else if(lastAnimationTime!==null)state.time+=(now-lastAnimationTime)/1000;
    if(state.loop&&state.selected&&state.time>=state.selected.end){seek(state.selected.start);if(audio.paused&&state.audioSession===state.session.track.id)audio.play().catch(()=>pause());}
    if(state.time>=state.session.track.duration){state.time=state.session.track.duration;pause();}
    if(now-lastDrawTime>=100){renderCurrent();lastDrawTime=now;}
    lastAnimationTime=now;
  }
  requestAnimationFrame(tick);
}
function parseClock(raw){const text=String(raw).trim();if(!/^(?:\d+:)?\d+(?:\.\d+)?$/.test(text))throw new Error('时间请填写秒数或 分:秒，例如 12.5 或 00:12.5。');const parts=text.split(':').map(Number);if(parts.length===2&&parts[1]>=60)throw new Error('分:秒格式中的秒数应小于 60。');return parts.length===2?parts[0]*60+parts[1]:parts[0];}
function editAnnotation(note=null,segment=null){
  pause();
  state.editing=note?.id??null;const selection=note??segment??state.selected;
  const start=selection?.start??Math.min(state.time,Math.max(0,state.session.track.duration-.5));
  const end=selection?.end??Math.min(state.session.track.duration,start+Math.min(5,state.session.track.duration));
  $('annotation-label').value=note?.label??'';$('annotation-start').value=formatTime(start);$('annotation-end').value=formatTime(end);$('annotation-notes').value=note?.notes??'';$('annotation-error').textContent='';$('delete-annotation').hidden=!note;
  state.annotationGroups=[...(selection?.groups??(state.focus?[state.focus]:[]))];renderAnnotationGroups();
  $('annotation-dialog').showModal();$('annotation-label').focus();
}
function renderAnnotationGroups(){document.querySelectorAll('[data-annotation-group]').forEach((button)=>button.setAttribute('aria-pressed',String(state.annotationGroups.includes(button.dataset.annotationGroup))));}
function saveAnnotation(event){event.preventDefault();try{
  const annotation={id:state.editing??uid(),start:parseClock($('annotation-start').value),end:parseClock($('annotation-end').value),label:$('annotation-label').value.trim(),groups:[...state.annotationGroups],notes:$('annotation-notes').value.trim()};
  if(!annotation.label)throw new Error('请给这段音乐起一个标题。');
  if(annotation.start<0||annotation.end<=annotation.start||annotation.end>state.session.track.duration)throw new Error(`请填写 0 至 ${clock(state.session.track.duration)} 内的起止时间，结束须晚于开始。`);
  const annotations=state.session.annotations.filter((item)=>item.id!==annotation.id);annotations.push(annotation);
  state.session=normalizeSession({...state.session,annotations});persist();renderTimeline();renderNotes();renderLibrary();$('annotation-dialog').close();toast(state.editing?'标注已更新':'标注已保存到本机');
}catch(error){$('annotation-error').textContent=error.message;}}
function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),15000);}
function safeName(){return state.session.track.title.replace(/[^\p{L}\p{N}._-]/gu,'_').slice(0,80)||'symphony';}
async function importSession(file){if(!file)return;try{
  if(file.size>8*1024*1024)throw new Error('请选择 8 MB 以内的会话 JSON。');const session=normalizeSession(JSON.parse(await file.text()));
  if(!session.source.label)session.source.label='用户导入的五组结果';
  const keepAudio=state.audioSession===session.track.id&&Math.abs(audio.duration-session.track.duration)<.15;
  setSession(session,{keepAudio});$('sources-dialog').close();toast(`已载入 ${session.frames.length} 个分析窗口与 ${session.annotations.length} 条标注`);
}catch(error){toast(`导入失败：${error.message}`);}}
async function loadAudio(file){if(!file)return;try{
  if(file.size>512*1024*1024)throw new Error('请选择 512 MB 以内的音频。');
  if(!/\.(wav|mp3|flac|ogg|m4a|aac|aiff?|opus|webm)$/i.test(file.name)&&!file.type.startsWith('audio/'))throw new Error('请选择 WAV、MP3、FLAC 等音频文件。');
  const candidate=new Audio();candidate.preload='metadata';const url=URL.createObjectURL(file);
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{candidate.src='';URL.revokeObjectURL(url);reject(new Error('音频读取超时，请尝试 WAV 或 MP3。'));},8000);candidate.onloadedmetadata=()=>{clearTimeout(timer);resolve();};candidate.onerror=()=>{clearTimeout(timer);URL.revokeObjectURL(url);reject(new Error('该文件未能解码，请尝试 WAV 或 MP3。'));};candidate.src=url;});
  const duration=candidate.duration;if(!Number.isFinite(duration)||duration<=0||duration>86400){candidate.src='';URL.revokeObjectURL(url);throw new Error('音频时长须大于 0 且不超过 24 小时。');}
  const sameManualAudio=state.session.source.kind==='manual'&&(state.session.source.uri===file.name||state.session.track.title===file.name.replace(/\.[^.]+$/,''));
  const canAttach=state.session.source.kind!=='demo'&&(sameManualAudio||state.session.source.kind!=='manual')&&Math.abs(state.session.track.duration-duration)<.15;
  const session=canAttach?state.session:{schema_version:1,source:{kind:'manual',label:'本地音频 · 人工标注',description:'载入识别结果后，可同时查看自动片段。',uri:file.name},track:{id:`audio-${Date.now()}`,title:file.name.replace(/\.[^.]+$/,''),duration,description:'本地音频 · 可播放、选段与手动标注'},frames:[],annotations:[]};
  setSession(session);state.audioURL=url;state.audioSession=state.session.track.id;audio.src=url;audio.load();candidate.src='';state.time=0;renderAll();$('sources-dialog').close();toast(canAttach?'音频已按时长关联到当前结果，请确认曲目一致。':'音频已载入，可以开始聆听和标注。');
}catch(error){toast(error.message);}}
async function importLog(file){if(!file)return;try{if(file.size>2*1024*1024)throw new Error('串口日志请控制在 2 MB 以内。');state.telemetry=parseTelemetry(await file.text());renderTelemetry();$('sources-dialog').showModal();toast('串口日志已载入板卡观测。');}catch(error){toast(`日志读取失败：${error.message}`);}}
function renderTelemetry(){const result=state.telemetry;if(!result)return;const last=result.observations.at(-1);$('telemetry-summary').hidden=false;$('telemetry-summary').textContent=`八类推理 ${result.observations.length} 次 · 心跳 ${result.heartbeats.length} 次 · 超时 ${result.timeouts.length} 次${last?`\n最近分类：${CLASS8[last.top1]??last.top1} · seq ${last.seq??'—'} · ${last.c} 周期\n末概率通道：${last.last_class}，值 ${last.last_p}%`:''}\n五组时间轴使用单独的五组结果数据。`;}
async function request(path,options){const response=await fetch(path,options);let data;try{data=await response.json();}catch{throw new Error('请通过 run.ps1 启动本地服务后再使用此功能。');}if(!response.ok)throw new Error(data.error?.message??data.message??(typeof data.error==='string'?data.error:`请求失败 ${response.status}`));return data;}
async function refreshPorts(){try{const data=await request('/api/ports');$('serial-port').replaceChildren();for(const port of data.ports??[]){const option=document.createElement('option');option.value=port.device??port.port??port;option.textContent=port.description?`${option.value} · ${port.description}`:option.value;$('serial-port').append(option);}if(!$('serial-port').options.length){const option=document.createElement('option');option.value='';option.textContent='暂无可用串口';$('serial-port').append(option);}$('serial-status').textContent=data.available===false?'串口连接需安装 pyserial；也可以直接导入已有日志。':'选择板卡串口后连接；当前会话的五组数据保持原值。';}catch{$('serial-status').textContent='启动本地服务后可连接板卡；日志导入可直接使用。';}}
async function connectSerial(){try{if(state.serialConnected){await request('/api/serial/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});state.serialConnected=false;$('connect-serial').textContent='连接';$('serial-status').textContent='串口已断开。';return;}const port=$('serial-port').value;if(!port)throw new Error('请先选择板卡串口。');await request('/api/serial/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port,baud:115200})});state.serialConnected=true;state.after=0;state.telemetry=parseTelemetry('');$('connect-serial').textContent='断开';$('serial-status').textContent=`正在接收 ${port} · 115200 baud`;}catch(error){$('serial-status').textContent=error.message;}}
async function pollTelemetry(){if(state.serialConnected)try{const data=await request(`/api/telemetry?after=${state.after}&limit=128`);state.after=data.next_after??state.after;const next=parseTelemetry((data.events??[]).map((event)=>event.line).join('\n'));for(const key of ['observations','heartbeats','timeouts'])state.telemetry[key]=[...state.telemetry[key],...next[key]].slice(-2000);renderTelemetry();if(data.status?.connected===false){state.serialConnected=false;$('connect-serial').textContent='连接';$('serial-status').textContent='连接已结束，可重新选择串口。';}}catch(error){state.serialConnected=false;$('serial-status').textContent=error.message;$('connect-serial').textContent='连接';}}
async function loadReferences(){try{state.reference=await request('/api/reference');$('reference-select').replaceChildren(...state.reference.samples.map((sample,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=`参考样本 ${index+1} · ${sample.active_groups.map((id)=>byGroup(id)?.nameZh??id).join('、')||'无活跃组'}`;return option;}));$('reference-picker').hidden=false;$('source-error').textContent='';}catch(error){$('source-error').textContent=error.message;}}
function chooseReference(){try{const sample=state.reference.samples[Number($('reference-select').value)];setSession({schema_version:1,source:{kind:'inference',label:'冻结模型独立参考样本',model:'group5_v3_float_20261102',description:'原模型参考输出 · 独立 1.5 秒窗口 · 无关联音频',uri:'models/group5_v3_float_20261102/reference_vectors.npz'},track:{id:sample.id,title:`五组模型 · 参考样本 ${Number($('reference-select').value)+1}`,duration:sample.duration_seconds,sample_rate:44100,description:'独立模型参考窗口，保留实际 activity 与 dominance 输出'},frames:[{id:sample.id,start:0,end:sample.duration_seconds,activity:sample.activities,dominance:sample.dominance}],annotations:[]});$('sources-dialog').close();toast('已载入现有模型的独立参考结果。');}catch(error){$('source-error').textContent=error.message;}}

$('nav-guide').addEventListener('click',()=>showView('guide'));$('nav-library').addEventListener('click',()=>showView('library'));
$('open-sources').addEventListener('click',()=>{$('sources-dialog').showModal();refreshPorts();});$('open-help').addEventListener('click',()=>$('help-dialog').showModal());
$('source-label').addEventListener('click',()=>{$('sources-dialog').showModal();refreshPorts();});
document.querySelectorAll('[data-close-dialog]').forEach((button)=>button.addEventListener('click',()=>button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach((dialog)=>dialog.addEventListener('click',(event)=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
for(const id of ['load-audio','source-load-audio'])$(id).addEventListener('click',()=>$('file-audio').click());
for(const id of ['import-session','source-import-session'])$(id).addEventListener('click',()=>$('file-session').click());
$('import-log').addEventListener('click',()=>$('file-log').click());
for(const [id,handler] of [['file-audio',loadAudio],['file-session',importSession],['file-log',importLog]])$(id).addEventListener('change',async(event)=>{await handler(event.target.files[0]);event.target.value='';});
$('demo-source').addEventListener('click',()=>{const saved=state.sessions.find((session)=>session.track.id==='demo-orchestra');setSession(saved??createDemoSession(),{time:21.5});$('sources-dialog').close();toast('已打开交互演示，演示不含音频。');});
$('reference-source').addEventListener('click',loadReferences);$('load-reference').addEventListener('click',chooseReference);
$('session-select').addEventListener('change',(event)=>{const session=state.sessions.find((item)=>item.track.id===event.target.value);if(session)setSession(session);});
for(const id of ['add-annotation','library-add-annotation','player-annotate'])$(id).addEventListener('click',()=>editAnnotation());
$('view-annotations').addEventListener('click',()=>{showView('library');$('segment-source').value='manual';renderLibrary();});
$('annotation-form').addEventListener('submit',saveAnnotation);
$('delete-annotation').addEventListener('click',()=>{state.session=normalizeSession({...state.session,annotations:state.session.annotations.filter((item)=>item.id!==state.editing)});persist();renderNotes();renderTimeline();renderLibrary();$('annotation-dialog').close();toast('标注已删除。');});
$('clear-focus').addEventListener('click',()=>{state.focus=null;renderTimeline();renderCurrent();});
for(const id of ['search-query','search-mode','segment-source','minimum-duration','dominant-only'])$(id).addEventListener(id==='search-query'?'input':'change',renderLibrary);
$('clear-filters').addEventListener('click',clearFilters);
$('export-json').addEventListener('click',()=>{try{download(`${safeName()}-session.json`,exportSessionJSON(state.session),'application/json;charset=utf-8');toast('完整会话已导出，保留数据来源与人工标注。');}catch(error){toast(error.message);}});
$('export-csv').addEventListener('click',()=>{try{download(`${safeName()}-segments.csv`,exportSegmentsCSV(filteredSegments(),{session:state.session}),'text/csv;charset=utf-8');toast('当前筛选片段已导出为 CSV。');}catch(error){toast(error.message);}});
$('play-toggle').addEventListener('click',()=>state.playing?pause():play());$('seek').addEventListener('input',(event)=>seek(Number(event.target.value)));$('skip-back').addEventListener('click',()=>seek(state.time-5));$('skip-forward').addEventListener('click',()=>seek(state.time+5));
$('loop-toggle').addEventListener('click',()=>{if(!state.selected){toast('先点击时间轴或检索结果，选择一个片段。');return;}state.loop=!state.loop;$('loop-toggle').setAttribute('aria-pressed',String(state.loop));toast(state.loop?'已开启所选片段循环':'已关闭片段循环');});
audio.addEventListener('ended',()=>{if(state.loop&&state.selected){seek(state.selected.start);play();}else{pause();state.time=Math.min(audio.duration,state.session.track.duration);renderCurrent();}});
document.addEventListener('keydown',(event)=>{if(event.ctrlKey||event.metaKey||event.altKey||document.querySelector('dialog[open]')||['INPUT','TEXTAREA','SELECT','BUTTON'].includes(document.activeElement?.tagName))return;if(event.code==='Space'){event.preventDefault();state.playing?pause():play();}else if(event.key==='ArrowLeft'){event.preventDefault();seek(state.time-5);}else if(event.key==='ArrowRight'){event.preventDefault();seek(state.time+5);}else if(event.key.toLowerCase()==='n'){event.preventDefault();editAnnotation();}else if(event.key==='/'){event.preventDefault();showView('library');$('search-query').focus();}});
$('refresh-ports').addEventListener('click',refreshPorts);$('connect-serial').addEventListener('click',connectSerial);
window.addEventListener('beforeunload',()=>{pause();if(state.audioURL)URL.revokeObjectURL(state.audioURL);});
restore();buildComponents();state.segments=deriveSegments(state.session.frames);persist();renderAll();showView(location.hash==='#library'?'library':'guide');requestAnimationFrame(tick);setInterval(pollTelemetry,1000);
request('/api/project').then((project)=>{if(project.live?.system_clock_hz)$('project-state').textContent=`${project.live.system_clock_hz/1e6} MHz · 八类板端 / 五组参考`;}).catch(()=>{$('project-state').textContent='本机工作台 · 文件导入可用';});
