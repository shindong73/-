(() => {
  'use strict';
  const DISPLAY_MS = 30000;
  const POLL_MS = 7000;
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
  function show(item) {
    active = true;
    remember(item.id);
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
    if (!item || typeof item.id !== 'string' || typeof item.title !== 'string'
      || !item.id || !item.title || seen[item.id] || queued.has(item.id)) return;
    if (!['politics','earthquake'].includes(item.kind)) return;
    const published = Date.parse(item.published_at);
    if (!Number.isFinite(published) || published < Date.now() - MAX_AGE_MS || published > Date.now() + 300000) return;
    queued.add(item.id);
    queue.push(item);
    queue.sort((a,b) => Number(b.kind==='earthquake') - Number(a.kind==='earthquake')
      || Date.parse(a.published_at) - Date.parse(b.published_at));
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
