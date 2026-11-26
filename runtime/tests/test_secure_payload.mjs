import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const temp = mkdtempSync(join(tmpdir(), 'news-encryption-test-'));
try {
  mkdirSync(join(temp, 'scripts'), {recursive:true});
  mkdirSync(join(temp, 'web'), {recursive:true});
  mkdirSync(join(temp, 'private'), {recursive:true});
  const names=['view.html','view.js','style.css','index.html','history.html','history.js','history.css'];
  for (const name of names) writeFileSync(join(temp,'web',name), 'fixture');
  const runner = join(temp, 'scripts', 'secure_payload.mjs');
  copyFileSync(join(root,'scripts','secure_payload.mjs'),runner);
  const env = {...process.env,
    VIEW_PASSPHRASE:'temporary-fixture-secret-is-at-least-32-characters',
    VIEW_LABEL:'NEWS ALERT'};
  const sample = {
    items:[{id:'story',kind:'politics',title:'국정원장 인선 발표',
            published_at:'2026-11-23T07:00:00Z'}],
    history:[{title:'국정원장 인선 발표',published_at:'2026-11-23T07:00:00Z'}],
    delivery_log:[{id:'story',title:'국정원장 인선 발표',kind:'politics',
                  detected_at:'2026-11-23T07:07:00Z'}],
    generated_at:'2026-11-23T07:07:00Z',
    last_scan_at:'2026-11-23T07:08:00Z',
    last_news_source_success_at:'2026-11-23T07:08:00Z',
    last_check_errors:[],
    selection_diagnostics:{
      rss_sources_ok:14,
      eligible_feed_articles:3,
      candidate_articles:1,
      newly_selected:1
    },
  };
  writeFileSync(join(temp,'private','payload.json'),JSON.stringify(sample));
  const run = mode => execFileSync('node',[runner,mode],
                                 {cwd:temp,env,encoding:'utf8'});
  run('publish');
  const cipherFile=join(temp,'data','payload.enc.json');
  const first=readFileSync(cipherFile,'utf8');
  assert.ok(!first.includes('국정원장'), 'plain headlines must not be published');
  assert.ok(existsSync(join(temp,'_deploy','history.html')));
  run('restore');
  const recovered=JSON.parse(readFileSync(join(temp,'private','payload.json'),'utf8'));
  for(const field of Object.keys(sample)) {
    assert.deepEqual(recovered[field],sample[field],field+' must survive roundtrip');
  }
  run('publish');
  assert.equal(readFileSync(cipherFile,'utf8'),first,'unchanged state should not re-encrypt');
  console.log('Encrypted feed restore/publish roundtrip OK');
} finally {
  rmSync(temp,{recursive:true,force:true});
}
