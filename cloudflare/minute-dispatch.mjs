/**
 * Cloudflare Cron Trigger for the existing OBS headline collector.
 * Cron: * * * * * (UTC, once per minute)
 * Secret: GITHUB_DISPATCH_TOKEN (fine-grained PAT, repo Actions: write only).
 */
const API_URL = "https://api.github.com/repos/shindong73/-/actions/workflows/refresh.yml/dispatches";

async function requestCollection(env, fetcher = fetch) {
  const token = String(env.GITHUB_DISPATCH_TOKEN || "").trim();
  if (!token) throw new Error("GITHUB_DISPATCH_TOKEN secret is missing");
  const response = await fetcher(API_URL, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": "Bearer " + token,
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "korean-obs-news-cron"
    },
    body: JSON.stringify({ref:"main", inputs:{task:"live"}})
  });
  if (!response.ok) {
    // Never print a secret, request headers, or error response body.
    throw new Error("GitHub workflow dispatch failed: HTTP " + response.status);
  }
  console.log("Dispatched GitHub news collection: HTTP " + response.status);
}

export { requestCollection };


/**
 * Optional encrypted caption-display audit API.
 * Requires the CAPTION_LOGS KV binding and CAPTION_LOG_SECRET Secret.
 * Secret must match the long passphrase already used by the overlay.
 * Only encrypted entries are persisted (never plaintext headlines).
 */
const CAPTION_PATH = "/caption-log";
const ALLOWED_ORIGIN = "https://shindong73.github.io";
function hex(bytes) {
  return [...new Uint8Array(bytes)].map(n => n.toString(16).padStart(2, "0")).join("");
}
async function authDigest(secret) {
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(secret)));
}
function apiHeaders(origin) {
  return {
    "Cache-Control": "no-store",
    "Vary": "Origin",
    ...(origin === ALLOWED_ORIGIN ? {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Authorization, Content-Type",
      "Access-Control-Max-Age": "600"
    } : {})
  };
}
function responseJson(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status, headers: {...apiHeaders(origin), "Content-Type": "application/json; charset=utf-8"}
  });
}
async function handleCaptionLog(request, env) {
  if (!request || !request.url) return new Response("Not found", {status:404});
  const url = new URL(request.url);
  if (url.pathname !== CAPTION_PATH) return new Response("Not found", {status:404});
  const origin = request.headers.get("Origin") || "";
  if (origin && origin !== ALLOWED_ORIGIN) return responseJson({error:"Origin denied"},403,origin);
  if (request.method === "OPTIONS") return new Response(null,{status:204,headers:apiHeaders(origin)});
  if (!["GET","POST"].includes(request.method)) return responseJson({error:"Method not allowed"},405,origin);
  const secret = String(env.CAPTION_LOG_SECRET || "");
  if (!env.CAPTION_LOGS || secret.length < 32)
    return responseJson({error:"Caption logging not configured"},503,origin);
  const expected = "Bearer " + await authDigest(secret);
  if (request.headers.get("Authorization") !== expected)
    return responseJson({error:"Not authorized"},401,origin);
  if (request.method === "GET") {
    const listed = await env.CAPTION_LOGS.list({prefix:"caption:",limit:500});
    return responseJson({
      entries:listed.keys.map(k => k.metadata).filter(m =>
        m && typeof m.started_at === "string" && m.v === 1
      ),
      has_more:!listed.list_complete
    },200,origin);
  }
  let data;
  try {data=await request.json();} catch (_) {return responseJson({error:"Invalid JSON"},400,origin);}
  if (!data || typeof data !== "object" || !/^[0-9a-f]{64}$/.test(data.id || "") ||
      data.v !== 1 || typeof data.started_at !== "string" ||
      !/^[A-Za-z0-9+/=]{12,64}$/.test(data.iv || "") ||
      !/^[A-Za-z0-9+/=]{24,850}$/.test(data.ct || "")) {
    return responseJson({error:"Invalid encrypted event"},400,origin);
  }
  const at = Date.parse(data.started_at);
  if (!Number.isFinite(at) || at < Date.now() - 30*86400000 || at > Date.now() + 300000)
    return responseJson({error:"Event time out of range"},400,origin);
  const metadata = {v:1,started_at:data.started_at,iv:data.iv,ct:data.ct};
  if (JSON.stringify(metadata).length > 1024)
    return responseJson({error:"Encrypted event too large"},413,origin);
  // Reverse timestamp makes KV's lexicographical listing newest-first.
  const reverse = String(9999999999999 - at).padStart(13,"0");
  const key = "caption:" + reverse + ":" + data.id;
  await env.CAPTION_LOGS.put(key,"",{
    metadata,expirationTtl:35*86400
  });
  return responseJson({saved:true},201,origin);
}

export default {
  async scheduled(controller, env, ctx) {
    // Logs show whether Cloudflare invoked the cron even if the GitHub API fails.
    console.log("OBS minute cron fired:", controller?.cron || "manual");
    ctx.waitUntil(requestCollection(env).catch(err => {
      // Only disclose a sanitized status or local error; never log auth data.
      console.error("OBS GitHub dispatch error:", err instanceof Error ? err.message : "unknown");
      throw err;
    }));
  },
  async fetch(request, env) {
    if (!request?.url) return new Response("Not found", {status:404});
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      // Read-only diagnostics; this endpoint never triggers GitHub Actions.
      return new Response(JSON.stringify({
        service:"OBS News Cron Trigger",
        version:"2026-11-23-diagnostics-v1",
        worker_deployed:true,
        github_token_configured:!!String(env?.GITHUB_DISPATCH_TOKEN || "").trim(),
        cron_status:"Check Cloudflare Triggers / Observability",
        dispatch_status:"Check GitHub Actions workflow_dispatch runs"
      }),{
        status:200,
        headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"}
      });
    }
    return handleCaptionLog(request, env);
  }
};
