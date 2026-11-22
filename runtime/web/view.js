(() => {
  'use strict';
  const DISPLAY_MS = 30000;
  const POLL_MS = 3000;
  const MAX_AGE_MS = 16 * 60 * 1000;
  const frame = document.querySelector('#frame');
  const bar = document.querySelector('#bar');
  const strip = document.querySelector('#red-strip');
  const headline = document.querySelector('#headline');
  const labelBox = document.querySelector('#label');
  const label = document.querySelector('#label-text');
  // The fragment is never sent to the web server; keep this URL secret.
  const password = new URLSearchParams(location.hash.slice(1)).get('key') || '';
  const STORAGE_KEY = 'view-state-v1';
  const DISPLAY_LOG_KEY = 'view-displayed-headlines-v1';
  const queue = [];
  const queued = new Set();
  let active = false;
  let seen = {};
  let lastPayload = '';
  let cryptoCache = {salt: null, key: null};
  try { seen = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {}; } catch (_) {}

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
  const foreignHeadline = /FBI|CIA|트럼프|바이든|푸틴|시진핑|젤렌스키|마크롱|다카이치|미국|미\s*연방|美\s*(?:대선|정부|대통령|공화|민주|의회|연방|법원|증시)|중국|中\s*(?:정부|당국|공산당|주석)|일본|日\s*(?:총리|정부|여당|야당)|러시아|우크라이나|대만|홍콩|북한|평양|김정은|영국|프랑스|독일|이탈리아|스페인|유럽|캐나다|호주|인도네시아|베트남|태국|필리핀|싱가포르|인도|파키스탄|이스라엘|팔레스타인|가자지구|이란|이라크|시리아|중동|멕시코|브라질|아르헨티나|아프리카|남미|국제\s*(?:뉴스|정세|사회|회의|기구|분쟁)|해외|외신|정상회담|외교장관|국제사회|유엔|미군|\b(?:EU|NATO|G7|G20)\b/i;
  // Do not infer Korea solely from generic words such as president or government.
  const domesticHeadline = /대한민국|한국|국내|우리나라|이재명|이\s*대통령|李\s*대통령|尹\s*대통령|윤석열|민주당|국민의힘|국힘|조국혁신당|정청래|김민석|조희대|추미애|국회|대통령실|청와대|국무회의|국무총리|국정|헌법재판소|헌재|대법원|검찰|특검|지방선거|수능|교육부|서울|경기|인천|부산|대구|광주|대전|울산|세종|충북|충남|경북|경남|전북|전남|강원|제주|여의도|용산|국회의원|행정안전부|기획재정부|금융위원회|민생|법무부/i;
  function allowBroadcast(item) {
    return item && (item.kind !== 'politics' ||
      (typeof item.title === 'string' && domesticHeadline.test(item.title) && !foreignHeadline.test(item.title)));
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
      try {
        const displayed = JSON.parse(localStorage.getItem(DISPLAY_LOG_KEY) || '[]');
        const log = Array.isArray(displayed) ? displayed : [];
        log.push({
          id:item.id, title:item.title, source:item.source || '',
          kind:item.kind, started_at:new Date().toISOString(),
          planned_duration_seconds:DISPLAY_MS / 1000
        });
        localStorage.setItem(DISPLAY_LOG_KEY, JSON.stringify(log.slice(-500)));
      } catch (_) { /* Never interrupt an overlay if device storage is disabled. */ }
    }
    headline.textContent = item.title;
    fitHeadline();
    bar.classList.remove('closing', 'visible');
    void bar.offsetWidth;
    bar.classList.add('visible');
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
    if (active || !queue.length) return;
    const item = queue.shift();
    queued.delete(item.id);
    show(item);
  }
  function offer(item) {
    if (!allowBroadcast(item)) return;
    if (!item || typeof item.id !== 'string' || typeof item.title !== 'string'
      || !item.id || !item.title || seen[item.id] || queued.has(item.id)) return;
    if (!['politics','earthquake'].includes(item.kind)) return;
    const discovered = Date.parse(item.detected_at || item.published_at);
    if (!Number.isFinite(discovered) || discovered < Date.now() - MAX_AGE_MS || discovered > Date.now() + 300000) return;
    queued.add(item.id);
    queue.push(item);
    queue.sort((a,b) => Number(b.kind==='earthquake') - Number(a.kind==='earthquake')
      || Date.parse(a.detected_at || a.published_at) - Date.parse(b.detected_at || b.published_at));
    next();
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
        if (raw === lastPayload) return;
        const data = await decrypt(JSON.parse(raw));
        if (!Array.isArray(data.items) || typeof data.label !== 'string') throw new Error('Invalid message');
        label.textContent = data.label;
        fitLabel();
        lastPayload = raw;
        for (const item of data.items) offer(item);
      } catch (_) {
        // Deliberately no visible error or plaintext fallback.
      } finally {
        polling = false;
      }
    }
    poll(); setInterval(poll, POLL_MS);
  }
})();
