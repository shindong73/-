(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const secret = new URLSearchParams(location.hash.slice(1)).get('key') || '';
  const STORE = 'view-displayed-headlines-v1';
  let server = [], client = [];
  let refreshing = false;
  const dateKst = value => {
    const n = Date.parse(value || '');
    return Number.isFinite(n) ? new Date(n).toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',
      hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false
    }) : '—';
  };
  function fromBase64(str) { return Uint8Array.from(atob(str), c => c.charCodeAt(0)); }
  async function decrypt(enc) {
    if (!secret || !crypto.subtle || enc.v !== 1) throw new Error('비밀키가 없거나 데이터 형식이 맞지 않습니다.');
    const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), 'PBKDF2', false, ['deriveKey']);
    const key = await crypto.subtle.deriveKey({
      name:'PBKDF2',salt:fromBase64(enc.salt),iterations:210000,hash:'SHA-256'
    },material,{name:'AES-GCM',length:256},false,['decrypt']);
    const decoded = await crypto.subtle.decrypt({name:'AES-GCM',iv:fromBase64(enc.iv),tagLength:128},key,fromBase64(enc.ct));
    return JSON.parse(new TextDecoder().decode(decoded));
  }
  function localLog() {
    try {const data=JSON.parse(localStorage.getItem(STORE) || '[]');return Array.isArray(data)?data:[];}
    catch(_){return [];}
  }
  function cell(row,text) {const td=document.createElement('td');td.textContent=String(text??'');row.appendChild(td);return td;}
  function render() {
    const q=$('query').value.trim().toLowerCase();
    const sent=$('sent'),shown=$('shown');
    sent.replaceChildren();shown.replaceChildren();
    const pass=r=>!q||String(r.title||'').toLowerCase().includes(q)||String(r.source||'').toLowerCase().includes(q);
    const selected=server.filter(pass);
    for(const r of selected) {
      const tr=document.createElement('tr');
      cell(tr,dateKst(r.detected_at));cell(tr,r.source);cell(tr,r.title);
      const td=document.createElement('td');
      if(typeof r.link==='string'&&/^https:\/\//.test(r.link)) {
        const a=document.createElement('a');a.href=r.link;a.textContent='기사 보기';a.target='_blank';a.rel='noopener noreferrer';td.appendChild(a);
      } else td.textContent='—';
      tr.appendChild(td);sent.appendChild(tr);
    }
    for(const r of client.filter(pass)) {
      const tr=document.createElement('tr');
      cell(tr,dateKst(r.started_at));cell(tr,r.source);cell(tr,r.title);cell(tr,(r.planned_duration_seconds||30)+'초');
      shown.appendChild(tr);
    }
    if(!selected.length){const tr=document.createElement('tr');const td=cell(tr,'표시할 기록이 없습니다.');td.colSpan=4;sent.appendChild(tr);}
    $('sent-count').textContent=server.length+'건';
    $('shown-count').textContent=client.length+'건';
    $('export').disabled=server.length===0;
  }
  function exportCsv(){
    const rows=[['발견시각(KST)','언론사','실제 방송용 헤드라인','기사 URL'],
      ...server.map(x=>[dateKst(x.detected_at),x.source,x.title,x.link||''])];
    const csv='\uFEFF'+rows.map(row=>row.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');
    const link=document.createElement('a'),url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    link.href=url;link.download='broadcast-feed-records.csv';link.click();URL.revokeObjectURL(url);
  }
  async function refresh(){
    if (refreshing) return;
    refreshing = true;
    $('status').textContent='암호화된 수집 기록 확인 중…';
    client=localLog().filter(x=>x&&x.kind&&x.title).reverse();
    try {
      const response=await fetch('./data/payload.enc.json?v='+Date.now(),{cache:'no-store'});
      if(!response.ok)throw new Error('데이터 요청 실패: '+response.status);
      const data=await decrypt(await response.json());
      server=(Array.isArray(data.delivery_log)?data.delivery_log:[]).filter(x=>x&&!x.is_test&&x.title).reverse();
      const scan = data.last_scan_at || data.generated_at;
      const age = Date.now() - Date.parse(scan || '');
      $('server-scan-at').textContent = dateKst(scan);
      $('status').textContent = !Number.isFinite(age)
        ? '마지막 수집 시각을 확인할 수 없습니다. GitHub Actions 실행 상태를 확인하세요.'
        : age > 30 * 60 * 1000
          ? '수집 지연 경고: 서버 수집 기록이 30분 이상 갱신되지 않았습니다. GitHub Actions 실행 상태를 확인하세요.'
          : '서버 선별 기록: 최근 최대 30일 · 1분 간격 자동 갱신 · 실제 OBS/송출 표시 여부는 별개';
      $('checked-at').textContent=dateKst(new Date().toISOString());
    }catch(e){
      $('status').textContent='기록 확인 실패. 주소 끝의 #key=비밀키를 확인하세요. '+(e?.message||'');
      server=[];
      $('server-scan-at').textContent='—';
    }
    render();
    refreshing = false;
  }
  $('query').addEventListener('input',render);
  $('refresh').addEventListener('click',refresh);
  $('export').addEventListener('click',exportCsv);
  refresh();
  setInterval(refresh, 60000);
})();
