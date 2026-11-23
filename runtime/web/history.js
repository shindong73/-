(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const secret = new URLSearchParams(location.hash.slice(1)).get('key') || '';
  const STORE = 'view-displayed-headlines-v1';
  // Fixed first-party Cloudflare endpoint; never send credentials to query-provided hosts.
  const LOG_API = new URLSearchParams(location.search).get('logApi') === 'off'
    ? '' : 'https://shindong-news-minute-trigger.kkireutv.workers.dev/caption-log';
  let remote = [], local = [], displayed = [];
  let refreshing = false, remoteError = '', scanError = '', scanAt = '';
  let captionKeyPromise = null;
  const dateKst = value => {
    const n = Date.parse(value || '');
    return Number.isFinite(n) ? new Date(n).toLocaleString('ko-KR', {
      timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',
      hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false
    }) : '—';
  };
  const fromBase64 = str => Uint8Array.from(atob(str), c => c.charCodeAt(0));
  const toHex = bytes => [...new Uint8Array(bytes)].map(n => n.toString(16).padStart(2,'0')).join('');
  function localLog() {
    try {
      const data = JSON.parse(localStorage.getItem(STORE) || '[]');
      return Array.isArray(data) ? data.filter(x => x && x.id && x.title && x.started_at && !x.is_test) : [];
    } catch (_) {return [];}
  }
  async function decryptFeed(enc) {
    if (!secret || !crypto.subtle || enc.v !== 1) throw Error('비밀키가 없거나 데이터 형식이 맞지 않습니다.');
    const material = await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),
      'PBKDF2',false,['deriveKey']);
    const key = await crypto.subtle.deriveKey({
      name:'PBKDF2',salt:fromBase64(enc.salt),iterations:210000,hash:'SHA-256'
    },material,{name:'AES-GCM',length:256},false,['decrypt']);
    const bytes=await crypto.subtle.decrypt({
      name:'AES-GCM',iv:fromBase64(enc.iv),tagLength:128
    },key,fromBase64(enc.ct));
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  function captionKey() {
    if (!captionKeyPromise) captionKeyPromise = (async () => {
      const material=await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),
        'PBKDF2',false,['deriveKey']);
      return crypto.subtle.deriveKey({
        name:'PBKDF2',salt:new TextEncoder().encode('obs-caption-log-v1'),
        iterations:210000,hash:'SHA-256'
      },material,{name:'AES-GCM',length:256},false,['decrypt']);
    })();
    return captionKeyPromise;
  }
  async function decryptShown(enc) {
    if (enc.v !== 1 || !enc.iv || !enc.ct) throw Error('Invalid encrypted caption');
    const bytes=await crypto.subtle.decrypt({
      name:'AES-GCM',iv:fromBase64(enc.iv),tagLength:128
    },await captionKey(),fromBase64(enc.ct));
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  function cell(row,txt) {
    const td=document.createElement('td');
    td.textContent=String(txt ?? '');
    row.appendChild(td);
    return td;
  }
  function mergeLogs() {
    const unique=new Map();
    // Remote records are authoritative for syncing, but confirm only display start.
    for(const record of remote) unique.set(record.id+'|'+record.started_at,
      {...record,place:'중앙 저장'});
    for(const record of local) {
      const id=record.id+'|'+record.started_at;
      if(!unique.has(id)) unique.set(id,{...record,place:'현재 브라우저'});
    }
    displayed=[...unique.values()].sort((a,b)=>
      Date.parse(b.started_at)-Date.parse(a.started_at));
  }
  function render() {
    const q=$('query').value.trim().toLowerCase();
    const filtered=displayed.filter(r => !q ||
      String(r.title||'').toLowerCase().includes(q) ||
      String(r.source||'').toLowerCase().includes(q));
    const shown=$('shown');
    shown.replaceChildren();
    for(const r of filtered) {
      const tr=document.createElement('tr');
      cell(tr,dateKst(r.started_at));
      cell(tr,r.source || '—');
      cell(tr,r.title);
      cell(tr,(Number(r.planned_duration_seconds)||30)+'초');
      cell(tr,r.place);
      shown.appendChild(tr);
    }
    if (!filtered.length) {
      const tr=document.createElement('tr');
      const td=cell(tr,'표시된 자막 기록이 없습니다.');
      td.colSpan=5; shown.appendChild(tr);
    }
    $('shown-count').textContent=displayed.length+'건';
    $('remote-count').textContent=remote.length+'건';
    $('export').disabled=!displayed.length;
    const localOnly=displayed.filter(x=>x.place==='현재 브라우저').length;
    const notes=[];
    if(!LOG_API) notes.push('중앙 기록 연동이 설정되지 않아 이 브라우저의 표시 기록만 확인할 수 있습니다. OBS 브라우저 소스와 기록이 공유되지 않을 수 있습니다.');
    else if(remoteError) notes.push('중앙 기록 확인 실패: '+remoteError+' (이 브라우저 기록만 표시될 수 있습니다.)');
    else notes.push('중앙 저장 기록 조회 성공. OBS 자막 화면에 표시가 시작된 기록이며 실제 생방송 송출 증명은 아닙니다.');
    if(localOnly) notes.push('현재 브라우저에만 남은 기록 '+localOnly+'건.');
    if(scanError) notes.push('수집 상태 확인 실패: '+scanError);
    else if(scanAt && Date.now()-Date.parse(scanAt)>30*60000)
      notes.push('뉴스 서버 수집이 30분 이상 갱신되지 않았습니다.');
    $('status').textContent=notes.join(' ');
  }
  function exportCsv() {
    const rows=[['표시 시작(KST)','언론사','화면에 표시된 자막','예정 시간(초)','기록 위치'],
      ...displayed.map(x=>[dateKst(x.started_at),x.source||'',x.title,
        x.planned_duration_seconds||30,x.place])];
    const csv='\uFEFF'+rows.map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');
    const link=document.createElement('a');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    link.href=url;link.download='obs-actual-displayed-captions.csv';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function loadRemote() {
    remote=[];
    remoteError='';
    if(!LOG_API) return;
    if(!secret) {remoteError='비밀키가 없습니다.';return;}
    try {
      const hash=toHex(await crypto.subtle.digest('SHA-256',
        new TextEncoder().encode(secret)));
      const response=await fetch(LOG_API,{
        mode:'cors',cache:'no-store',headers:{Authorization:'Bearer '+hash}
      });
      if(!response.ok) throw Error('HTTP '+response.status);
      const data=await response.json();
      if(!Array.isArray(data.entries)) throw Error('잘못된 기록 형식');
      const values=await Promise.all(data.entries.map(async entry => {
        try {
          const row=await decryptShown(entry);
          return row && row.id && row.title && row.started_at ? row : null;
        } catch (_) {return null;}
      }));
      remote=values.filter(Boolean);
      if(data.has_more) remoteError='최근 500건만 표시됩니다. 오래된 기록은 조회 범위 밖에 있습니다.';
    } catch(e) {remoteError=e?.message || '연결 오류';}
  }
  async function loadScan() {
    scanAt='';scanError='';
    if(!secret) {scanError='암호화 키가 없습니다.';return;}
    try {
      const response=await fetch('./data/payload.enc.json?v='+Date.now(),{cache:'no-store'});
      if(!response.ok) throw Error('HTTP '+response.status);
      const data=await decryptFeed(await response.json());
      scanAt=data.last_scan_at || data.generated_at || '';
    } catch(e) {scanError=e?.message || '연결 오류';}
  }
  async function refresh() {
    if(refreshing) return;
    refreshing=true;
    $('status').textContent='실제 자막 표시 기록 확인 중…';
    local=localLog();
    await Promise.all([loadRemote(),loadScan()]);
    mergeLogs();
    $('server-scan-at').textContent=dateKst(scanAt);
    $('checked-at').textContent=dateKst(new Date().toISOString());
    render();
    refreshing=false;
  }
  $('query').addEventListener('input',render);
  $('refresh').addEventListener('click',refresh);
  $('export').addEventListener('click',exportCsv);
  refresh();
  // Stay within Cloudflare KV free-list quota; manual refresh stays immediate.
  setInterval(() => { if (!document.hidden) refresh(); },180000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
