'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="vp-token"]').content;
let report = null, timer = null, busy = false, generation = 0;
async function api(path, body) {
  const response = await fetch(path, {method:body === undefined ? 'GET':'POST', headers:{'X-VoiceProof-Token':token}, body});
  if (!response.ok) {
    let message = '本机连接失败，请确认服务仍在运行后重试。';
    try { message = (await response.json()).error || message; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}
function message(text, error=false) { $('status').textContent=text; $('status').className=error?'error':''; }
function setBusy(value) { busy=value; $('submit').disabled=value; $('setup').disabled=value; }
function timestamp(value) { return `${Math.floor(value/60).toString().padStart(2,'0')}:${(value%60).toFixed(1).padStart(4,'0')}`; }
function node(tag, text, cls) { const element=document.createElement(tag); if(text!==undefined) element.textContent=text; if(cls)element.className=cls; return element; }
function play(start) { const player=$('player'); player.currentTime=Math.max(0,start-.5); player.play().catch(()=>message('无法播放，请重新检查或确认浏览器允许音频播放。',true)); }
function conclusion() {
  if(report.issues.some(i=>i.state==='confirmed')) return '必须重录';
  if(report.issues.some(i=>i.state==='review')) return '建议复核';
  return '可忽略（仍需完整回听）';
}
const stateLabel = {review:'建议复核',confirmed:'必须重录',ignored:'可忽略'};
function render() {
  $('report').hidden=false; $('empty').hidden=true; $('conclusion').textContent=conclusion(); $('warning').textContent=report.warning;
  $('issues').replaceChildren();
  for(const issue of report.issues.filter(i=>$('filter').value==='all'||i.state===$('filter').value)) {
    const card=node('article',undefined,`issue ${issue.state}`);
    const hear=node('button',`▶ ${timestamp(issue.start)}`,'time'); hear.type='button'; hear.onclick=()=>play(issue.start);
    const heading=node('h4',issue.label); heading.append(node('span',stateLabel[issue.state],'badge')); card.append(hear,heading);
    if(issue.expected)card.append(node('p',`原稿：${issue.expected}`));
    if(issue.observed)card.append(node('p',`识别：${issue.observed}`));
    card.append(node('p',`${issue.timing}${issue.confidence!==null?` · ASR置信线索 ${Math.round(issue.confidence*100)}%（非错误概率）`:''}`));
    const actions=node('div',undefined,'actions');
    for(const [text,state] of [['回听确认有问题','confirmed'],['忽略此项','ignored'],['待复核','review']]) {
      const button=node('button',text); button.type='button'; button.onclick=()=>{issue.state=state;render();}; actions.append(button);
    }
    card.append(actions); $('issues').append(card);
  }
  if(!$('issues').children.length)$('issues').append(node('p','此筛选下没有问题。请在发布前完整回听。'));
  $('transcript').replaceChildren();
  for(const segment of report.transcript) { const button=node('button',`${timestamp(segment.start)}  ${segment.text}`,'segment'); button.type='button';button.onclick=()=>play(segment.start);$('transcript').append(button); }
}
async function poll() {
  const mine=generation;
  clearTimeout(timer);
  try {
    const status=await api('/status'); if(mine!==generation)return; $('engine').textContent=status.ready?'本地语音引擎已就绪':'尚未安装本地语音引擎';
    $('setup').hidden=status.ready; message(status.message,status.state==='failed'); setBusy(status.state==='running');
    if(status.state==='running') timer=setTimeout(poll,1000);
    if(status.state==='done') { report=status.report; $('player').src='/media';render(); }
  } catch(error) { if(mine===generation){setBusy(false);message(error.message,true);} }
}
$('check-form').onsubmit=async event=>{
  event.preventDefault(); if(busy)return;
  const file=$('media').files[0];
  if(!file||file.size===0||file.size>100*1024*1024) {message('请选择非空且不超过100MB的音视频文件。',true);return;}
  const mine=++generation; report=null;$('filter').value='all';$('report').hidden=true;$('empty').hidden=false;$('clear').disabled=true;
  setBusy(true);message('正在读取素材，全部处理都在本机进行…');
  try { await api('/check',new FormData($('check-form')));if(mine===generation)await poll(); } catch(error){if(mine===generation){setBusy(false);message(error.message,true);}}finally{$('clear').disabled=false;}
};
$('setup').onclick=async()=>{++generation;setBusy(true);message('正在准备下载本地模型…');try{await api('/setup',new FormData());await poll();}catch(error){setBusy(false);message(error.message,true);}};
$('clear').onclick=async()=>{
  ++generation;clearTimeout(timer);$('player').pause();$('player').removeAttribute('src');$('player').load();
  try {await api('/clear',new FormData()); report=null;$('report').hidden=true;$('empty').hidden=false;$('check-form').reset();$('script-file').value='';setBusy(false);message('本次素材与报告已删除，可重新开始。');}catch(error){message(error.message,true);}
};
$('script-file').onchange=async()=>{const file=$('script-file').files[0];if(!file)return;if(file.size>100000){message('原稿文件过大，请选择20000字以内的 UTF-8 文本。',true);return;}try{const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());if(text.length>20000)throw Error();$('script').value=text;}catch(_){message('无法读取原稿，请使用 UTF-8 文本，最多20000字。',true);}};
$('filter').onchange=()=>{if(report)render();};
$('export').onclick=()=>{
  if(!report)return;
  const lines=['VoiceProof 声检 · 本机复核报告',`结论：${conclusion()}`,report.warning,'时间点为估计；用户确认的项目表示必须重录。',...report.issues.map(i=>`${timestamp(i.start)} ${i.label} / ${stateLabel[i.state]}\n原稿：${i.expected}\n识别：${i.observed}\n定位：${i.timing}`)];
  const url=URL.createObjectURL(new Blob([lines.join('\n\n')],{type:'text/plain;charset=utf-8'}));const link=node('a');link.href=url;link.download='VoiceProof-复核报告.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
poll();
