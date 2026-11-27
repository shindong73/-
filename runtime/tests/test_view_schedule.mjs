import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runInNewContext} from 'node:vm';

const view = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'web','view.js'), 'utf8');
const from = view.indexOf('  function show(item) {');
const to = view.indexOf('  function fromBase64(b64) {', from);
const readyFrom = view.indexOf('  function captionGapMs(item) {');
const readyTo = view.indexOf('  let lastPayload',readyFrom);
assert.ok(from > 0 && to > from && readyFrom > 0 && readyTo > readyFrom);
assert.ok(view.includes('const MAX_AGE_MS = 50 * 60 * 1000;'),
  'selected politics must remain available while the priority queue drains');
assert.ok(view.includes('const REGULAR_GAP_MS = 2 * 60 * 1000;'),
  'ordinary news should use a 2-minute gap');
assert.ok(view.includes('const MAJOR_GAP_MS = 45 * 1000;'),
  'major breaking news should use a 45-second gap');
assert.ok(view.includes('const DISPLAY_MS = 40000;'),
  '40-second display duration must remain unchanged');
assert.ok(view.includes('const WARNING_MAX_AGE_MS = 15 * 60 * 1000;'),
  'civil-defense warnings must keep their short age limit');
assert.ok(view.includes('if (raw === lastPayload && !DIAGNOSE) { next(); return; }'),
  'unchanged payload must continue driving queued captions; diagnostics stay live');
assert.ok(view.includes('localStorage.getItem(LAST_DISPLAY_AT_KEY)'),
  'cooldown must survive OBS browser reload');
assert.ok(view.includes("const DIAGNOSE = new URLSearchParams(location.search).get('diagnose') === '1';"),
  'diagnostic mode must be explicit opt-in');
assert.ok(view.includes("if (LOG_API && !DIAGNOSE) setInterval(syncDisplayedLog,60000);"),
  'read-only diagnostic page must not upload old browser display logs');
const diagStart=view.indexOf('        if (DIAGNOSE) {',view.indexOf('    async function poll()'));
const mainDisplay=view.indexOf('        for (const item of data.items) offer(item);',diagStart);
assert.ok(diagStart>0 && mainDisplay>diagStart
  && view.slice(diagStart,mainDisplay).includes('          return;'),
  'diagnostic page must return before normal queue offer and display');
const historyHtml=readFileSync(join(dirname(fileURLToPath(import.meta.url)),
  '..','web','history.html'),'utf8');
assert.ok(historyHtml.includes('id="diagnose-view"'),
  'history must expose an OBS connection diagnostic action');

let clock = Date.parse('2026-11-26T00:00:00Z');
const scheduled = [];
const records = [];
const stored = new Map();
const DateStub = class extends Date {
  static now() { return clock; }
  static parse(value) { return Date.parse(value); }
};
const classList = {add(){},remove(){}};
const context = {
  Date: DateStub,
  window: {setTimeout(fn,ms) {scheduled.push({when:clock+ms,fn});}},
  bar:{classList,offsetWidth:5},
  headline:{textContent:''},
  localStorage:{setItem(k,v){stored.set(k,v);}},
  fitHeadline(){},
  recordDisplay(item){records.push(item.id);},
  allowBroadcast(item) {return item.id !== 'rejected';}
};
const harness = `(() => {
  const DISPLAY_MS = 40000, MAX_AGE_MS = 50 * 60000;
  const WARNING_MAX_AGE_MS = 15 * 60000;
  const maxDisplayAge = item => item?.kind === 'warning' ? WARNING_MAX_AGE_MS : MAX_AGE_MS;
  const REGULAR_GAP_MS = 2 * 60000;
  const MAJOR_GAP_MS = 45 * 1000;
  const MAJOR_PRIORITY = 90;
  const LAST_DISPLAY_AT_KEY = 'view-last-news-display-v1';
  let lastDisplayAt = 0, active = false;
  const seen = {}, queue = [], queued = new Set();
  function remember(id){seen[id] = Date.now();}
  ${view.slice(readyFrom,readyTo)}
  ${view.slice(from,to)}
  return {offer,next,seen,queue,queued,canStartCaption,state:()=>({lastDisplayAt,active})};
})()`;
const ticker = runInNewContext(harness, context);
const article = (id,kind='politics',priority=90) => ({
  id,kind,priority,title:'국회가 예산안 가결',source_title:'국회, 예산안 가결',
  published_at:new Date(clock).toISOString(),detected_at:new Date(clock).toISOString()
});
function advance(ms) {
  const limit=clock+ms;
  while (scheduled.some(x=>x.when <= limit)) {
    scheduled.sort((a,b)=>a.when-b.when);
    const next=scheduled.shift();
    if(next.when>limit){scheduled.unshift(next);break;}
    clock=next.when;next.fn();
  }
  clock=limit;
}
// Three simultaneous major stories: show consecutively about every 45 seconds
// (after each 40s caption), not 12 minutes apart.
ticker.offer(article('first'));ticker.offer(article('second'));ticker.offer(article('third'));
ticker.next();
assert.deepEqual(records,['first'],'first major story must start immediately');
assert.equal(Number(stored.get('view-last-news-display-v1')),clock);
assert.equal(ticker.canStartCaption({is_manual:true},clock),true,
  'operator manual caption bypasses the automatic cooldown');
assert.equal(ticker.canStartCaption({kind:'warning'},clock),true,
  'civil-defense warning bypasses the automatic cooldown');
assert.equal(ticker.canStartCaption({kind:'politics',priority:90},clock),false,
  'a second major story waits until 45 seconds after first start');
assert.equal(ticker.canStartCaption({kind:'politics',priority:60},clock),false,
  'ordinary news waits 2 minutes after last start');
advance(30360);
assert.equal(ticker.state().active,true,
  'caption must remain visible at 30 seconds of 40-second duration');
advance(10000);
assert.equal(ticker.state().active,false,
  'caption must finish after 40 seconds and close animation');
assert.deepEqual(records,['first'],'second article must wait a few seconds after the first');
assert.equal(ticker.queue.length,2,'queued articles must remain until displayed');
advance(4550);
ticker.next();
assert.deepEqual(records,['first'],'major news must not appear before 45-second mark');
advance(200);
ticker.next();
assert.deepEqual(records,['first','second'],
  'second important article starts after about 45 seconds, not 12 minutes');
advance(44900);
ticker.next();
assert.deepEqual(records,['first','second'],
  'third headline must wait for the new 45-second interval');
advance(200);
ticker.next();
assert.deepEqual(records,['first','second','third'],
  'third headline is broadcast after about 90 seconds from first');
assert.equal(ticker.seen.third>0,true);

// Non-major news still respects the two-minute start-to-start protection.
advance(40500);
ticker.offer(article('normal','politics',60));
ticker.next();
assert.deepEqual(records,['first','second','third']);
advance(79400);
ticker.next();
assert.deepEqual(records,['first','second','third'],
  'normal news must not run before the 2-minute interval');
advance(200);
ticker.next();
assert.deepEqual(records,['first','second','third','normal'],
  'normal headline becomes eligible after 2 minutes');

// A confirmed civil-defense warning runs directly after a currently shown
// 40-second caption, rather than waiting for normal news cooldown.
ticker.offer(article('warning-now','warning',100));
advance(40360);
assert.deepEqual(records,['first','second','third','normal','warning-now'],
  'an urgent warning starts as soon as the prior caption closes');
advance(40360);
const oldWarning = {...article('expired-warning','warning',100),
  detected_at:'2026-11-25T00:00:00Z'};
ticker.offer(oldWarning);
assert.equal(ticker.queued.has('expired-warning'),false,
  'expired civil-defense warnings must never be reintroduced');

// OBS hidden scenes may NOT consume a news caption or falsely record it
// as displayed. Once visible, a queued major headline can be sent.
const hiddenArticle=article('only-while-visible','politics',95);
ticker.offer(hiddenArticle);
context.window.obsstudio={pluginVersion:'test'};
context.document={visibilityState:'hidden'};
advance(5000);
ticker.next();
assert.equal(records.includes('only-while-visible'),false,
  'hidden OBS source must not consume a caption');
assert.equal(ticker.seen['only-while-visible'],undefined,
  'hidden OBS source must not mark a caption as seen');
context.document.visibilityState='visible';
ticker.next();
assert.equal(records.includes('only-while-visible'),true,
  'returning to visible OBS scene displays the queued item');

// Manual caption bypasses automatic gap, but never overlaps an active bar.
ticker.offer({...article('manual-now','politics',200),
  is_manual:true,source:'직접 입력'});
advance(40360);
assert.equal(records.at(-1),'manual-now',
  'manual headline broadcasts after current caption closes');
assert.ok(view.includes('다음 기사 대기: '),
  'diagnosis must show the current pending item cooldown');
assert.ok(view.includes('송출 간격: 일반 2분 / 주요 45초'),
  'diagnosis must explain the new adaptive schedule');
assert.ok(view.includes('일반 브라우저(OBS와 별도 상태)'),
  'browser diagnosis must not claim to represent actual OBS');

const logFrom = view.indexOf('  let volatileDisplayedLog = [];');
const logTo = view.indexOf('  async function syncDisplayedLog()',logFrom);
assert.ok(logFrom > 0 && logTo > logFrom);
const logMemory = runInNewContext(`(() => {
  const DISPLAY_LOG_KEY = 'view-displayed-headlines-v1';
  const DISPLAY_MS = 40000, LOG_API = '';
  const localStorage = {
    getItem(){return null;},
    setItem(){throw new Error('QuotaExceededError');}
  };
  ${view.slice(logFrom,logTo)}
  return {recordDisplay,displayedLog,persistDisplayedLog};
})()`);
logMemory.recordDisplay({id:'log-1',kind:'politics',source:'KBS',title:'국회가 법안 가결'});
assert.equal(logMemory.displayedLog()[0].planned_duration_seconds,40,
  'actual display-start records must use 40 seconds');
logMemory.recordDisplay({id:'log-2',kind:'politics',source:'MBC',title:'정부가 중대 결정 발표'});
assert.equal(logMemory.displayedLog().length,2,
  'central-sync queue must retain new display records if localStorage fails');
const saved=logMemory.displayedLog();
saved[0].synced_to_server=true;
logMemory.persistDisplayedLog(saved);
assert.equal(logMemory.displayedLog().filter(x=>!x.synced_to_server).length,1,
  'synced display records must stay acknowledged in the memory fallback');

const versionHtml = readFileSync(join(dirname(fileURLToPath(import.meta.url)),
  '..','web','view.html'),'utf8');
const expectedVersion=view.match(/const SCRIPT_VERSION = '([A-Za-z0-9_-]+)'/);
assert.ok(expectedVersion && versionHtml.includes('view.js?v='+expectedVersion[1]),
  'the HTML cache-busting script version and running client version must match');
const updateStart = view.indexOf('    async function checkClientVersion() {');
const updateEnd = view.indexOf('    setInterval(checkClientVersion',updateStart);
assert.ok(updateStart > 0 && updateEnd > updateStart);
let reloads=0;
let remoteVersion=expectedVersion[1];
const updateClient=runInNewContext(`(() => {
  let active=false;
  const SCRIPT_VERSION = '${expectedVersion[1]}';
  ${view.slice(updateStart,updateEnd)}
  return {checkClientVersion,setActive(v){active=v}};
})()`,{
  Date:DateStub,
  fetch:async()=>({ok:true,text:async()=>'<script src="./view.js?v='+remoteVersion+'"></script>'}),
  location:{reload(){reloads++;}}
});
await updateClient.checkClientVersion();
assert.equal(reloads,0,'do not reload when script has not changed');
remoteVersion='newer-client-build';
updateClient.setActive(true);
await updateClient.checkClientVersion();
assert.equal(reloads,0,'do not interrupt a 40-second active caption for a code update');
updateClient.setActive(false);
await updateClient.checkClientVersion();
assert.equal(reloads,1,'apply future code updates when OBS is idle');

console.log('OBS adaptive schedule, 40-second bar, crash-safe logs and version checks OK');
