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

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(requestCollection(env));
  },
  async fetch() {
    // No publicly accessible trigger endpoint, even with the Worker URL.
    return new Response("Not found", {status:404});
  }
};
