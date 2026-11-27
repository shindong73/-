(() => {
  'use strict';
  const SCRIPT_VERSION = 'hearing-reports-20261127c';
  const DISPLAY_MS = 30000;
  // Minimum interval between the START of two actual news captions.
  const MIN_DISPLAY_GAP_MS = 12 * 60 * 1000;
  const LAST_DISPLAY_AT_KEY = 'view-last-news-display-v1';
  const POLL_MS = 3000;
  // Keep accepted politics available through multiple 12-minute captions.
  // Never replay a civil-defense warning outside its short 15-minute window.
  const MAX_AGE_MS = 50 * 60 * 1000;
  const WARNING_MAX_AGE_MS = 15 * 60 * 1000;
  const maxDisplayAge = item => item?.kind === 'warning' ? WARNING_MAX_AGE_MS : MAX_AGE_MS;
  const frame = document.querySelector('#frame');
  const bar = document.querySelector('#bar');
  const strip = document.querySelector('#red-strip');
  const headline = document.querySelector('#headline');
  const labelBox = document.querySelector('#label');
  const label = document.querySelector('#label-text');
  // The fragment is never sent to the web server; keep this URL secret.
  const password = new URLSearchParams(location.hash.slice(1)).get('key') || '';
  // Opt-in, read-only diagnosis. The status page never broadcasts a caption,
  // modifies viewer seen-state, or writes a false "display started" log.
  const DIAGNOSE = new URLSearchParams(location.search).get('diagnose') === '1';
  let diagnosticBox = null;
  function showDiagnostics(message) {
    if (!DIAGNOSE) return;
    if (!diagnosticBox) {
      diagnosticBox = document.createElement('div');
      diagnosticBox.id = 'obs-diagnostic';
      Object.assign(diagnosticBox.style, {
        position:'fixed',left:'24px',top:'24px',right:'24px',
        zIndex:'99999',padding:'18px 22px',
        background:'rgba(0,0,0,.92)',color:'white',
        fontFamily:'sans-serif',fontSize:'22px',lineHeight:'1.5',
        whiteSpace:'pre-wrap',overflowWrap:'anywhere',
        maxWidth:'900px',borderRadius:'12px'
      });
      document.body.appendChild(diagnosticBox);
    }
    diagnosticBox.textContent = 'OBS 속보 점검 (읽기 전용)' + String.fromCharCode(10) + message.replaceAll('\\n', String.fromCharCode(10));
  }
  if (DIAGNOSE) showDiagnostics(password
    ? '암호화된 뉴스 피드 연결 중…'
    : '비밀키 누락: 주소 끝에 #key=가 없어 뉴스 피드를 열 수 없습니다.');
  const STORAGE_KEY = 'view-state-v1';
  const DISPLAY_LOG_KEY = 'view-displayed-headlines-v1';

  // Optional central history. Without logApi the browser-only log still works.
  // Example: view.html?logApi=https%3A%2F%2Fyour-worker.workers.dev#key=...
  // Fixed first-party Cloudflare endpoint; never send credentials to query-provided hosts.
  const LOG_API = new URLSearchParams(location.search).get('logApi') === 'off'
    ? '' : 'https://shindong-news-minute-trigger.kkireutv.workers.dev/caption-log';
  let syncingLog = false;
  let captionKeyPromise = null;
  let authHashPromise = null;
  const toB64 = bytes => btoa(String.fromCharCode(...bytes));
  const toHex = bytes => [...new Uint8Array(bytes)].map(n => n.toString(16).padStart(2,'0')).join('');
  function captionKey() {
    if (!captionKeyPromise) captionKeyPromise = (async () => {
      const material = await crypto.subtle.importKey('raw',new TextEncoder().encode(password),
        'PBKDF2',false,['deriveKey']);
      return crypto.subtle.deriveKey({
        name:'PBKDF2',salt:new TextEncoder().encode('obs-caption-log-v1'),
        iterations:210000,hash:'SHA-256'
      },material,{name:'AES-GCM',length:256},false,['encrypt']);
    })();
    return captionKeyPromise;
  }
  function authHash() {
    if (!authHashPromise) authHashPromise = crypto.subtle.digest('SHA-256',
      new TextEncoder().encode(password)).then(toHex);
    return authHashPromise;
  }
  // In OBS browser contexts storage can fail (quota/private source). Preserve
  // unsynced display-start records in memory so the encrypted KV API still
  // receives them and a storage error cannot silently erase the new event.
  let volatileDisplayedLog = [];
  function displayedLog() {
    let persisted = [];
    try {
      const records = JSON.parse(localStorage.getItem(DISPLAY_LOG_KEY) || '[]');
      if (Array.isArray(records)) persisted = records;
    } catch (_) {}
    const unique = new Map();
    for (const row of [...persisted, ...volatileDisplayedLog]) {
      if (row && typeof row.id === 'string' && typeof row.started_at === 'string') {
        unique.set(row.id + '|' + row.started_at, row);
      }
    }
    return [...unique.values()].slice(-500);
  }
  function persistDisplayedLog(records) {
    volatileDisplayedLog = records.slice(-500);
    try {
      localStorage.setItem(DISPLAY_LOG_KEY, JSON.stringify(volatileDisplayedLog));
    } catch (_) { /* Central encrypted transmission can still succeed. */ }
  }
  function recordDisplay(item) {
    // This means the overlay started displaying, not that OBS was live/on-air.
    const log=displayedLog();
    log.push({
      id:item.id,title:item.title,source:item.source || '',kind:item.kind,
      started_at:new Date().toISOString(),planned_duration_seconds:DISPLAY_MS/1000,
      synced_to_server:false
    });
    persistDisplayedLog(log);
    if (LOG_API) void syncDisplayedLog();
  }
  async function syncDisplayedLog() {
    if (!LOG_API || !password || syncingLog || !crypto.subtle) return;
    syncingLog = true;
    try {
      const records=displayedLog();
      for (const row of records.filter(x => x && x.id && x.title && x.started_at &&
        !x.synced_to_server && !x.is_test &&
        Date.parse(x.started_at) > Date.now()-30*86400000).slice(-20)) {
        const id=toHex(await crypto.subtle.digest('SHA-256',
          new TextEncoder().encode(row.id + '|' + row.started_at)));
        const iv=crypto.getRandomValues(new Uint8Array(12));
        const event={
          id:row.id,title:row.title,source:row.source || '',kind:row.kind || '',
          started_at:row.started_at,planned_duration_seconds:row.planned_duration_seconds || 30
        };
        const ct=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},
          await captionKey(),new TextEncoder().encode(JSON.stringify(event))));
        const response=await fetch(LOG_API,{
          method:'POST',mode:'cors',cache:'no-store',
          headers:{'Content-Type':'application/json','Authorization':'Bearer '+await authHash()},
          body:JSON.stringify({id,started_at:row.started_at,v:1,iv:toB64(iv),ct:toB64(ct)})
        });
        if (!response.ok) break;
        const current=displayedLog();
        const match=current.find(x=>x.id===row.id&&x.started_at===row.started_at);
        if(match) {
          match.synced_to_server=true;
          persistDisplayedLog(current);
        }
      }
    } catch (_) {
      // Keep unsynced logs locally; retry without disturbing the on-screen headline.
    } finally { syncingLog=false; }
  }
  if (LOG_API && !DIAGNOSE) setInterval(syncDisplayedLog,60000);

  const queue = [];
  const queued = new Set();
  let active = false;
  let seen = {};
  let lastDisplayAt = 0;
  try {
    const stored = Number(localStorage.getItem(LAST_DISPLAY_AT_KEY));
    if (Number.isFinite(stored) && stored > 0 && stored <= Date.now() + 300000) {
      lastDisplayAt = stored;
    }
  } catch (_) { /* An unavailable storage backend must not break the ticker. */ }
  function canStartCaption(item, now = Date.now()) {
    return item?.is_test === true || now - lastDisplayAt >= MIN_DISPLAY_GAP_MS;
  }
  let lastPayload = '';
  let cryptoCache = {salt: null, key: null};
  try {
    const previous = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (previous && typeof previous === 'object' && !Array.isArray(previous)) {
      seen = previous;
    }
  } catch (_) { /* Malformed local state must not interrupt the overlay. */ }

  function remember(id) {
    seen[id] = Date.now();
    seen = Object.fromEntries(Object.entries(seen).filter(([, time]) => Number(time) > Date.now() - 48 * 3600000).slice(-400));
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(seen)); } catch (_) {}
  }
  // Preserve the reference artwork's geometry across 16:9 source sizes.
  // On portrait sources, place the scaled 16:9 artboard at the bottom.
  function fitFrame() {
    const scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    const left = (window.innerWidth - 1920 * scale) / 2;
    const top = window.innerHeight - 1080 * scale;
    frame.style.transform = `translate(${left}px, ${top}px) scale(${scale})`;
  }
  // Short headlines: relax negative tracking toward the natural width (max: 0px).
  // Long headlines: keep the 150px font size and compress horizontally as needed.
  // Never stretch characters beyond their undistorted (scaleX(1)) proportions.
  function fitHeadline() {
    headline.style.transform = 'scaleX(1)';
    headline.style.letterSpacing = '';
    strip.style.justifyContent = 'flex-start';
    if (!headline.textContent) return;
    const boxStyle = getComputedStyle(strip);
    const available = strip.clientWidth -
      parseFloat(boxStyle.paddingLeft) - parseFloat(boxStyle.paddingRight);
    if (!(available > 0)) return;
    const compactWidth = headline.scrollWidth;
    if (compactWidth > available) {
      headline.style.transform = `scaleX(${available / compactWidth})`;
      return;
    }
    // The compact text fits. Increase only the *spaces between letters*,
    // not the glyphs, up to SUITE's original, unexpanded proportions.
    headline.style.letterSpacing = '0px';
    const naturalWidth = headline.scrollWidth;
    if (naturalWidth < available) {
      // If there is still room, balance the unused space on both sides.
      strip.style.justifyContent = 'center';
      return;
    }
    // Choose tracking between -0.105em and 0px to fill the strip.
    const fontSize = parseFloat(getComputedStyle(headline).fontSize) || 150;
    let lo = -0.105 * fontSize;
    let hi = 0;
    for (let i = 0; i < 16; i++) {
      const mid = (lo + hi) / 2;
      headline.style.letterSpacing = mid + 'px';
      if (headline.scrollWidth > available) hi = mid;
      else lo = mid;
    }
    headline.style.letterSpacing = lo + 'px';
  }
  function fitLabel() {
    label.style.transform = 'scaleX(1)';
    label.style.letterSpacing = '';
    const available = labelBox.clientWidth -
      parseFloat(getComputedStyle(labelBox).paddingLeft) -
      parseFloat(getComputedStyle(labelBox).paddingRight);
    const measured = label.scrollWidth;
    if (measured > available && available > 0) {
      label.style.transform = `scaleX(${available / measured})`;
    }
  }
  function refreshGeometry() {
    fitFrame();
    fitLabel();
    if (headline.textContent) fitHeadline();
  }
  refreshGeometry();
  window.addEventListener('resize', refreshGeometry);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(refreshGeometry);
  // Defense in depth: old encrypted queues must not replay foreign headlines.
  // The server applies a more comprehensive domestic-only rule before selection.
  const foreignHeadline = /FBI|CIA|트럼프|바이든|푸틴|시진핑|젤렌스키|마크롱|다카이치|미국|미\s*연방|美\s*(?:대선|정부|대통령|공화|민주|의회|연방|법원|증시)|중국|中\s*(?:정부|당국|공산당|주석)|일본|日\s*(?:총리|정부|여당|야당)|러시아|우크라이나|대만|홍콩|북한|평양|김정은|영국|프랑스|독일|이탈리아|스페인|유럽|캐나다|호주|인도네시아|베트남|태국|필리핀|싱가포르|인도|파키스탄|이스라엘|팔레스타인|가자지구|이란|이라크|시리아|중동|멕시코|브라질|아르헨티나|남아공|남아프리카공화국|에티오피아|페루|칠레|콜롬비아|나이지리아|케냐|튀르키예|튀르키에|사우디|말레이시아|뉴질랜드|폴란드|스웨덴|네덜란드|스위스|아프리카|남미|국제\s*(?:뉴스|정세|사회|회의|기구|분쟁)|해외|외신|정상회담|국제사회|유엔|미군|\b(?:EU|NATO|G7|G20)\b/i;
  // Do not infer Korea solely from generic words such as president or government.
  const domesticHeadline = /대한민국|한국|국내|우리나라|이재명|이\s*대통령|李\s*대통령|尹\s*대통령|윤석열|최교진|최민희|민주당|국민의힘|국힘|조국혁신당|정청래|김민석|조희대|추미애|국회|법사위|법제사법위원회|인사청문|청문보고서|대통령실|청와대|국무회의|국무총리|국정|정부|헌법재판소|헌재|대법원|검찰|특검|지방선거|수능|교육부|서울|경기|인천|부산|대구|광주|대전|울산|세종|충북|충남|경북|경남|전북|전남|강원|제주|여의도|용산|국회의원|행정안전부|기획재정부|금융위원회|민생|법무부|보건복지부|복지부|국토교통부|국토부|고용노동부|노동부|금융감독원|경찰청|기상청|산업통상부|국정원장|국가정보원|개각|외교부|외교장관|통일부|통일장관|행안부|행안장관|문체부|문체장관|문화체육관광부|강금실|임웅순|홍익표|한준호|강유정/i;
  // Same policy on the browser, to stop replay of previously queued commentary.
  const partyOpinion = /(?:국민의힘|국힘|더불어민주당|민주당|민주|조국혁신당|혁신당)\s*(?:대변인|대표|원내대표)?\s*(?:[:,：，]\s*)?["“‘'「『]/;
  const partyReaction = /(?:국민의힘|국힘|더불어민주당|민주당|민주|조국혁신당|혁신당).{0,55}?(?:논평|반박|비판|비난|규탄|공세|책임론|공방|못\s*믿|끝날\s*일\s*아냐|끝날\s*일\s*아니|끝날\s*문제\s*아니|사퇴로\s*끝날|사퇴만으론|사퇴에\s*그쳐선|책임\s*물어야)/;
  // Defense in depth: old queued and shortened headlines must not bypass
  // user-excluded election topics or low-impact local personnel news.
  // Source-exclusive labels are never eligible even after the title is rewritten.
  const exclusiveTag = /[\[［【(（]\s*단독(?:\s*보도)?\s*[\]］】)）]/;
  const excludedPartyTopic = /조국\s*혁신당|혁신당/;
  const excludedElectionTopic = /선\s*관\s*위|선거\s*관리\s*위원회|부정\s*선거|선거\s*(?:조작|부정)|(?:사전\s*)?(?:투표|개표|투표지|투표함)\s*(?:조작|부정)|(?:조작|부정)\s*(?:투표|개표|투표지|투표함)/;
  const minorLocalPost = /경제자유구역청(?:장)?|부시장|부지사|부군수|부구청장|(?:시청|도청|군청|구청).{0,35}?(?:국장|과장|실장|본부장|센터장|사업소장)|(?:도시|관광|시설관리|교통|환경|개발|문화|체육)\s*(?:공사|공단|재단).{0,18}?(?:이사장|사장|대표|원장|본부장)|(?:시|도|군|구)\s*(?:산하|소속).{0,30}?(?:국장|과장|실장|본부장|센터장|이사장|사장|대표)/;
  const personnelAction = /사의|사표|사직서|사퇴|사임|경질|해임|교체|발탁|내정|지명|임명/;
  function excludedHeadline(text) {
    return exclusiveTag.test(text) || excludedElectionTopic.test(text) ||
      excludedPartyTopic.test(text) ||
      (personnelAction.test(text) && minorLocalPost.test(text));
  }
  function normalizedPublisherTitle(text) {
    return String(text || '')
      .replace(/^\s*(?:\[\s*(?:속보|긴급)\s*\]|【\s*속보\s*】|(?:속보|긴급)\s*[:：])\s*/,'')
      .replace(/\s+/g,' ').trim();
  }
  function allowBroadcast(item) {
    if (!item || typeof item.title !== 'string' || !item.title.trim()) return false;
    // USGS is disabled by request. Reject old encrypted queues and any
    // reintroduced source, even before their 16-minute feed TTL expires.
    if (String(item.source || '').trim().toUpperCase() === 'USGS'
        || String(item.id || '').toLowerCase().startsWith('usgs-')) return false;
    const sourceTitle = typeof item.source_title === 'string' ? item.source_title : '';
    if (excludedHeadline(item.title) || excludedHeadline(sourceTitle)) return false;
    if (item.kind === 'warning') {
      // A warning has a sanitized regional headline. Military or missile
      // developments must never bypass this gate as a generic alert.
      const original = typeof item.source_title === 'string' && item.source_title.trim()
        ? item.source_title : item.title;
      return /^[가-힣0-9·\s-]{2,35} 경계경보 (?:발령|해제|정정)$/.test(item.title)
        && /경계\s*경보/.test(original)
        && /(?:발령|해제|정정)/.test(original)
        && !/(?:북한|미사일|탄도탄|발사체|ICBM)/.test(item.title)
        && !/(?:훈련|모의|가상|예고|예정|가능성|검토|테스트)/.test(original);
    }
    // Earthquake simulation remains possible only through explicit manual tests;
    // no live earthquake item can be replayed from earlier encrypted feeds.
    if (item.kind !== 'politics') {
      return item.kind === 'earthquake' && item.is_test === true
        && String(item.source || '').includes('방송 테스트');
    }
    // Never display a publisher-original sentence as the scrolling headline.
    // Legacy feed entries without an original cannot prove their rewrite.
    if (!sourceTitle || normalizedPublisherTitle(sourceTitle) ===
        normalizedPublisherTitle(item.title)) return false;
    // No AI bypasses. Every item, including historical AI selections, must
    // pass the same local editorial safety gate before reaching OBS.
    // Apply the browser's last-resort editorial safety gate to the ORIGINAL
    // publisher headline. The broadcast rewrite can omit the Korean actor,
    // even when the server correctly approved a major domestic event.
    // Never use an untrusted shortened caption to bypass party-opinion checks.
    const original = typeof item.source_title === 'string' && item.source_title.trim()
      ? item.source_title : item.title;
    return domesticHeadline.test(original)
      && !foreignHeadline.test(original)
      && !/(?:미사일|탄도탄|탄도미사일|발사체|ICBM|SLBM)/i.test(original)
      && !partyOpinion.test(original)
      && !partyReaction.test(original);
  }
  function show(item) {
    if (!allowBroadcast(item)) {
      remember(item.id);
      active = false;
      next();
      return;
    }
    active = true;
    remember(item.id);
    if (!item.is_test) {
      lastDisplayAt = Date.now();
      try { localStorage.setItem(LAST_DISPLAY_AT_KEY, String(lastDisplayAt)); } catch (_) {}
    }
    headline.textContent = item.title;
    fitHeadline();
    bar.classList.remove('closing', 'visible');
    void bar.offsetWidth;
    bar.classList.add('visible');
    if (!item.is_test) recordDisplay(item);
    window.setTimeout(() => {
      bar.classList.remove('visible');
      bar.classList.add('closing');
      window.setTimeout(() => {
        bar.classList.remove('closing');
        active = false;
        next();
      }, 360);
    }, DISPLAY_MS);
  }
  function next() {
    if (active) return;
    // OBS keeps browser sources alive even when their scene or source is hidden
    // (unless "Shutdown source when not visible" is enabled). Do not consume
    // an article or report a display-start event while OBS cannot show it.
    if (window.obsstudio && document.visibilityState === 'hidden') return;
    while (queue.length) {
      const item = queue[0];
      const discovered = Date.parse(item.detected_at || item.published_at);
      // A large backlog must never play expired news after its 16-minute TTL.
      if (!Number.isFinite(discovered) || discovered < Date.now() - maxDisplayAge(item) ||
          discovered > Date.now() + 300000 || seen[item.id] || !allowBroadcast(item)) {
        queue.shift();
        queued.delete(item.id);
        continue;
      }
      // Leave the item queued while another headline is in its 12-minute
      // cooldown. An unchanged encrypted feed still calls next() every poll.
      if (!canStartCaption(item)) return;
      queue.shift();
      queued.delete(item.id);
      show(item);
      return;
    }
  }
  function offer(item) {
    if (!allowBroadcast(item)) return;
    if (!item || typeof item.id !== 'string' || typeof item.title !== 'string'
      || !item.id || !item.title || seen[item.id] || queued.has(item.id)) return;
    if (!['politics','earthquake','warning'].includes(item.kind)) return;
    const discovered = Date.parse(item.detected_at || item.published_at);
    if (!Number.isFinite(discovered) || discovered < Date.now() - maxDisplayAge(item) || discovered > Date.now() + 300000) return;
    queued.add(item.id);
    queue.push(item);
    queue.sort((a,b) => Number(b.kind==='warning') - Number(a.kind==='warning')
      || (Number(b.priority) || 0) - (Number(a.priority) || 0)
      || Date.parse(a.detected_at || a.published_at) - Date.parse(b.detected_at || b.published_at));
  }
  function fromBase64(b64) {
    const raw = atob(b64);
    return Uint8Array.from(raw, c => c.charCodeAt(0));
  }
  async function decrypt(envelope) {
    if (envelope.v !== 1 || !envelope.salt || !envelope.iv || !envelope.ct) throw new Error('Invalid data');
    if (!cryptoCache.key || cryptoCache.salt !== envelope.salt) {
      const secret = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']);
      const key = await crypto.subtle.deriveKey({name:'PBKDF2',salt:fromBase64(envelope.salt),iterations:210000,hash:'SHA-256'}, secret, {name:'AES-GCM',length:256}, false, ['decrypt']);
      cryptoCache = {salt: envelope.salt, key};
    }
    const plaintext = await crypto.subtle.decrypt({name:'AES-GCM',iv:fromBase64(envelope.iv),tagLength:128}, cryptoCache.key, fromBase64(envelope.ct));
    return JSON.parse(new TextDecoder().decode(plaintext));
  }

  if (password && window.crypto && crypto.subtle) {
    // Without the key the overlay stays completely blank; no labels or events.
    let polling = false;
    async function poll() {
      if (polling) return;
      polling = true;
      try {
        const r = await fetch('./data/payload.enc.json?v=' + Date.now(), {cache:'no-store'});
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const raw = await r.text();
        // A queued caption can become eligible after 12 minutes without any
        // change to the feed, so keep advancing the queue during steady-state.
        if (raw === lastPayload && !DIAGNOSE) { next(); return; }
        const data = await decrypt(JSON.parse(raw));
        if (!Array.isArray(data.items) || typeof data.label !== 'string') throw new Error('Invalid message');
        label.textContent = data.label;
        fitLabel();
        lastPayload = raw;
        if (DIAGNOSE) {
          const now = Date.now();
          const eligible = data.items.filter(x => x
            && typeof x.id === 'string'
            && allowBroadcast(x)
            && Number.isFinite(Date.parse(x.detected_at || x.published_at))
            && Date.parse(x.detected_at || x.published_at) >= now-maxDisplayAge(x)
            && Date.parse(x.detected_at || x.published_at) <= now+300000);
          const alreadyHandled = eligible.filter(x => !!seen[x.id]).length;
          const pending = eligible.length - alreadyHandled;
          const cooldownSeconds = Math.max(0, Math.ceil(
            (MIN_DISPLAY_GAP_MS - (now-lastDisplayAt))/1000
          ));
          const isOBS = !!window.obsstudio;
          const isHiddenOBS = isOBS && document.visibilityState === 'hidden';
          const stat = data.selection_diagnostics || {};
          const reason = !eligible.length
            ? '현재 화면에 표시할 유효한 기사가 없습니다.'
            : isHiddenOBS
              ? 'OBS 브라우저 소스가 숨겨져 있습니다. 활성 장면 및 소스 표시 상태를 확인하세요.'
              : !pending
                ? '이 브라우저에서 해당 기사를 이미 처리한 것으로 기록했습니다.'
                : cooldownSeconds > 0
                  ? '마지막 자막 이후 12분 제한으로 대기 중입니다.'
                  : '이 브라우저에서는 표시할 수 있습니다. 실제 OBS 소스의 URL과 활성 상태를 확인하세요.';
          showDiagnostics(
            '암호화 피드 복호화 성공\\n' +
            '실행 환경: ' + (isOBS ? 'OBS 브라우저 소스' : '일반 브라우저(OBS와 별도 상태)') + '\\n' +
            '브라우저 가시성: ' + (document.visibilityState || '확인 불가') + '\\n' +
            '현재 서버 대기 기사: ' + data.items.length + '건\\n' +
            '기사 규칙·유효기간 통과: ' + eligible.length + '건\\n' +
            '이 브라우저에서 이미 처리한 기사: ' + alreadyHandled + '건\\n' +
            '이 브라우저의 미처리 기사: ' + pending + '건\\n' +
            '12분 제한 잔여: ' + Math.ceil(cooldownSeconds/60) + '분\\n' +
            '최근 수집 경로 성공: ' + (Number(stat.rss_sources_ok)||0) + '개\\n' +
            '최근 신규 선정: ' + (Number(stat.newly_selected)||0) + '건\\n' +
            '판단: ' + reason
          );
          return;
        }
        // Latest feed is authoritative: abandon articles removed by the
        // tighter editorial policy before they appear in OBS.
        const allowed = new Set(data.items.filter(x => x && typeof x.id === 'string').map(x => x.id));
        for (let i = queue.length - 1; i >= 0; i--) {
          if (!allowed.has(queue[i].id)) {
            queued.delete(queue[i].id);
            queue.splice(i, 1);
          }
        }
        for (const item of data.items) offer(item);
        next();
      } catch (error) {
        // The real OBS overlay remains blank on error to avoid misreporting;
        // opt-in diagnosis shows a safe code, never the secret or the feed.
        if (DIAGNOSE) showDiagnostics(
          error?.name === 'OperationError'
            ? '복호화 실패: OBS URL의 #key= 값이 현재 암호화 키와 일치하는지 확인하세요.'
            : '데이터 수신/처리 오류: ' + String(error?.name || 'Error') +
              ' (서버 접근·네트워크·스크립트 호환성 확인)'
        );
      } finally {
        polling = false;
      }
    }
    poll(); setInterval(poll, POLL_MS);
    // A long-running OBS browser source does not automatically reload
    // JavaScript after GitHub Pages deploys a new client. Check the tiny HTML
    // shell occasionally and reload ONLY while no caption is actively shown.
    async function checkClientVersion() {
      if (active) return;
      try {
        const r = await fetch('./view.html?version-check=' + Date.now(), {cache:'no-store'});
        if (!r.ok) return;
        const match = (await r.text()).match(/view\.js\?v=([A-Za-z0-9_-]+)/);
        if (match && match[1] !== SCRIPT_VERSION) location.reload();
      } catch (_) { /* Network issues must never interrupt a live caption. */ }
    }
    setInterval(checkClientVersion, 5 * 60 * 1000);
  } else if (DIAGNOSE && password) {
    showDiagnostics('이 브라우저는 WebCrypto 암호화 기능을 지원하지 않아 속보를 복호화할 수 없습니다.');
  }
})();
