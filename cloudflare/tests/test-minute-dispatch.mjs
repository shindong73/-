import assert from "node:assert/strict";
import worker, {requestCollection} from "../minute-dispatch.mjs";

const secret="only-a-test-token";
const calls=[];
const mockFetch=async(url,opts)=>{calls.push({url,opts});return{ok:true,status:204};};
await requestCollection({GITHUB_DISPATCH_TOKEN:secret},mockFetch);
assert.equal(calls.length,1);
assert.equal(calls[0].url,
  "https://api.github.com/repos/shindong73/-/actions/workflows/refresh.yml/dispatches");
assert.equal(calls[0].opts.method,"POST");
assert.equal(calls[0].opts.headers.Authorization,"Bearer "+secret);
assert.deepEqual(JSON.parse(calls[0].opts.body),
  {ref:"main",inputs:{task:"live"}});
assert.equal((await worker.fetch()).status,404);
await assert.rejects(requestCollection({},mockFetch),/secret is missing/);
await assert.rejects(
  requestCollection({GITHUB_DISPATCH_TOKEN:secret},async()=>({ok:false,status:403})),
  /HTTP 403/
);
console.log("Cloudflare minute dispatch tests OK");

const logSecret = "unit-test-caption-secret-at-least-32-characters";
const kvSaved=new Map();
const kv={
  async put(key, val, opts) {kvSaved.set(key,opts.metadata);},
  async list({prefix,limit}) {
    return {keys:[...kvSaved].filter(([k])=>k.startsWith(prefix))
      .sort(([a],[b])=>a.localeCompare(b)).slice(0,limit)
      .map(([name,metadata])=>({name,metadata})),list_complete:true};
  }
};
const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(logSecret));
const hash=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");
const env={CAPTION_LOG_SECRET:logSecret,CAPTION_LOGS:kv};
const url="https://test.example.workers.dev/caption-log";
const origin="https://shindong73.github.io";
const entry={
  id:"a".repeat(64), started_at:new Date().toISOString(),
  v:1, iv:"AAECAwQFBgcICQoL",ct:"AAECAwQFBgcICQoLDA0ODxAREhMUFRYX"
};
const headers={"Authorization":"Bearer "+hash,"Origin":origin,"Content-Type":"application/json"};
const put=await worker.fetch(new Request(url,{method:"POST",headers,body:JSON.stringify(entry)}),env);
assert.equal(put.status,201);
assert.equal(kvSaved.size,1);
const get=await worker.fetch(new Request(url,{headers}),env);
assert.equal(get.status,200);
assert.equal(get.headers.get("Access-Control-Allow-Origin"),origin);
const results=await get.json();
assert.equal(results.entries.length,1);
assert.equal(results.entries[0].started_at,entry.started_at);
assert.equal(results.entries[0].ct,entry.ct);
const unauthorized=await worker.fetch(new Request(url,{headers:{"Authorization":"Bearer invalid","Origin":origin}}),env);
assert.equal(unauthorized.status,401);
const noStore=await worker.fetch(new Request(url,{headers}),{CAPTION_LOG_SECRET:logSecret});
assert.equal(noStore.status,503);
const wrongOrigin=await worker.fetch(new Request(url,{headers:{...headers,Origin:"https://evil.example"}}),env);
assert.equal(wrongOrigin.status,403);
assert.equal((await worker.fetch(new Request("https://test.example.workers.dev/"),env)).status,404);
console.log("Encrypted caption display logging API tests OK");

const healthUrl = "https://test.example.workers.dev/health";
const health = await worker.fetch(new Request(healthUrl),{GITHUB_DISPATCH_TOKEN:secret});
assert.equal(health.status,200);
assert.equal(health.headers.get("Cache-Control"),"no-store");
assert.equal((await health.json()).github_token_configured,true);
const noTokenHealth=await worker.fetch(new Request(healthUrl),{});
assert.equal((await noTokenHealth.json()).github_token_configured,false);
assert.equal((await worker.fetch(new Request(healthUrl,{method:"POST"}),{})).status,404);
// Exercise actual scheduled() invocation without sending a real API request.
const oldFetch = globalThis.fetch;
globalThis.fetch = mockFetch;
try {
  const promises=[];
  await worker.scheduled({cron:"* * * * *"},{GITHUB_DISPATCH_TOKEN:secret},{
    waitUntil(p) {promises.push(p);}
  });
  assert.equal(promises.length,1);
  await Promise.all(promises);
  assert.equal(calls.length,2);
} finally { globalThis.fetch=oldFetch; }
console.log("Cron scheduled() and read-only health endpoint tests OK");

