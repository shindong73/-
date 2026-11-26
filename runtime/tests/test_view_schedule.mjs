import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runInNewContext} from 'node:vm';

const view = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'web','view.js'), 'utf8');
const from = view.indexOf('  function show(item) {');
const to = view.indexOf('  function fromBase64(b64) {', from);
const readyFrom = view.indexOf('  function canStartCaption(item, now = Date.now()) {');
const readyTo = view.indexOf('  let lastPayload',readyFrom);
assert.ok(from > 0 && to > from && readyFrom > 0 && readyTo > readyFrom);
assert.ok(view.includes('const MAX_AGE_MS = 50 * 60 * 1000;'),
  'selected politics must remain available across several 12-minute cooldowns');
assert.ok(view.includes('const WARNING_MAX_AGE_MS = 15 * 60 * 1000;'),
  'civil-defense warnings must keep their short age limit');
assert.ok(view.includes('if (raw === lastPayload) { next(); return; }'),
  'unchanged payload must continue driving queued captions');
assert.ok(view.includes('localStorage.getItem(LAST_DISPLAY_AT_KEY)'),
  'cooldown must survive OBS browser reload');

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
  const DISPLAY_MS = 30000, MAX_AGE_MS = 50 * 60000;
  const WARNING_MAX_AGE_MS = 15 * 60000;
  const maxDisplayAge = item => item?.kind === 'warning' ? WARNING_MAX_AGE_MS : MAX_AGE_MS;
  const MIN_DISPLAY_GAP_MS = 12 * 60000;
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
ticker.offer(article('first'));ticker.offer(article('second'));ticker.offer(article('third'));
ticker.next();
assert.deepEqual(records,['first'],'first story must start immediately');
assert.equal(Number(stored.get('view-last-news-display-v1')),clock);
advance(30360);
assert.deepEqual(records,['first'],'second must not start immediately after 30-second caption');
assert.equal(ticker.queue.length,2,'queued articles must not disappear during cooldown');
advance(11*60000);
ticker.next();
assert.deepEqual(records,['first'],'cooldown must enforce 12 minutes since first start');
advance(12*60000-(clock-Date.parse('2026-11-26T00:00:00Z'))+100);
ticker.next();
assert.deepEqual(records,['first','second'],'next item should show at 12-minute mark');
assert.equal(ticker.seen.second>0,true);
advance(12*60000+100);
ticker.next();
assert.deepEqual(records,['first','second','third'],
  'third selected headline must reach OBS 24 minutes later instead of expiring at 16 minutes');
const oldWarning = {...article('expired-warning','warning',100),
  detected_at:'2026-11-26T00:00:00Z'};
ticker.offer(oldWarning);
assert.equal(ticker.queued.has('expired-warning'),false,
  'old civil-defense warning must never be resurrected by the longer politics queue');
const logFrom = view.indexOf('  let volatileDisplayedLog = [];');
const logTo = view.indexOf('  async function syncDisplayedLog()',logFrom);
assert.ok(logFrom > 0 && logTo > logFrom);
const logMemory = runInNewContext(`(() => {
  const DISPLAY_LOG_KEY = 'view-displayed-headlines-v1';
  const DISPLAY_MS = 30000, LOG_API = '';
  const localStorage = {
    getItem(){return null;},
    setItem(){throw new Error('QuotaExceededError');}
  };
  ${view.slice(logFrom,logTo)}
  return {recordDisplay,displayedLog,persistDisplayedLog};
})()`);
logMemory.recordDisplay({id:'log-1',kind:'politics',source:'KBS',title:'국회가 법안 가결'});
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
assert.equal(reloads,0,'do not interrupt a 30-second active caption for a code update');
updateClient.setActive(false);
await updateClient.checkClientVersion();
assert.equal(reloads,1,'apply future code updates when OBS is idle');

console.log('OBS 12-minute schedule, crash-safe caption logs and client version checks OK');
