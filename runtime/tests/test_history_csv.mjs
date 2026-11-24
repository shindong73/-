import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=join(dirname(fileURLToPath(import.meta.url)),'..','web');
const source=readFileSync(join(root,'history.js'),'utf8');
const start=source.indexOf('  function csvCell(value) {');
const end=source.indexOf('  function exportCsv() {',start);
assert.ok(start>=0 && end>start, 'CSV escaping function missing');
const csvCell=new Function(source.slice(start,end)+'return csvCell;')();
assert.equal(csvCell('normal " quote'), '"normal "" quote"');
for(const input of ['=HYPERLINK("https://phishing.example")','+CMD','-1+3','@SUM(1,2)','\t=2+2','  =2+2']) {
  const result=csvCell(input);
  assert.ok(result.startsWith('"\''), 'unsafe CSV spreadsheet formula: '+input);
}
assert.equal(csvCell('국회 예산안 통과'),'"국회 예산안 통과"');
assert.ok(source.includes('마지막 정상 기록 유지'), 'Remote failure should retain previous records');
assert.ok(source.includes('last_news_source_success_at'), 'RSS heartbeat must be monitored');
assert.ok(source.includes('Array.isArray(data.delivery_log)'), 'Selected headlines must load from encrypted server feed');
assert.ok(source.includes("const displayedIds=new Set(displayed.map(r=>r.id))"), 'Server selection and actual captions must be reconciled');
const html=readFileSync(join(root,'history.html'),'utf8');
assert.ok(html.includes('id="selected"'), 'Selected headlines need a separate audit table');
assert.ok(html.includes('id="shown"'), 'Actual displayed captions need a separate table');
console.log('CSV formula safety and history-state regression tests OK');
