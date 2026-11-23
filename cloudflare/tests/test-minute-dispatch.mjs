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
