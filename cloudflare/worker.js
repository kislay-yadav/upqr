/**
 * Cloudflare Worker — Telegram Webhook Failover Router
 *
 * Receives all Telegram updates at a single stable URL.
 * Forwards to PRIMARY (Railway); falls back to BACKUP (Render) if primary is unhealthy.
 *
 * Environment Variables (set in Cloudflare Worker dashboard):
 *   CF_PRIMARY_URL      — e.g. https://myqrro.railway.app
 *   CF_BACKUP_URL       — e.g. https://myqrro.onrender.com
 *   CF_WEBHOOK_SECRET   — same secret used in BOT_TOKEN webhook setup
 *   CF_HEALTH_TIMEOUT   — ms before health check times out (default: 3000)
 *
 * Set Telegram webhook to:
 *   https://your-worker.your-subdomain.workers.dev/webhook/<CF_WEBHOOK_SECRET>
 */

const HEALTH_CACHE_TTL_MS = 15_000;   // re-check health every 15 s
const FORWARD_TIMEOUT_MS  = 25_000;   // max time to wait for upstream

let _primaryHealthy    = true;
let _lastHealthCheck   = 0;

// ── Health checker ────────────────────────────────────────────────────────

async function checkHealth(baseUrl, timeoutMs) {
  const controller = new AbortController();
  const tid = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${baseUrl}/health`, { signal: controller.signal });
    clearTimeout(tid);
    if (!res.ok) return false;
    const body = await res.json();
    return body.status === "ok";
  } catch {
    clearTimeout(tid);
    return false;
  }
}

async function resolvePrimary(env) {
  const now = Date.now();
  if (now - _lastHealthCheck < HEALTH_CACHE_TTL_MS) {
    return _primaryHealthy;
  }
  _lastHealthCheck = now;
  const timeout = parseInt(env.CF_HEALTH_TIMEOUT || "3000", 10);
  _primaryHealthy = await checkHealth(env.CF_PRIMARY_URL, timeout);
  return _primaryHealthy;
}

// ── Request forwarder ─────────────────────────────────────────────────────

async function forwardRequest(targetBase, path, request, secret) {
  const url        = `${targetBase}${path}`;
  const controller = new AbortController();
  const tid        = setTimeout(() => controller.abort(), FORWARD_TIMEOUT_MS);

  try {
    const body = await request.arrayBuffer();
    const res  = await fetch(url, {
      method:  "POST",
      headers: {
        "Content-Type":           "application/json",
        "X-Telegram-Bot-Api-Secret-Token": secret,
      },
      body,
      signal: controller.signal,
    });
    clearTimeout(tid);
    return res;
  } catch (err) {
    clearTimeout(tid);
    throw err;
  }
}

// ── Main handler ──────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url  = new URL(request.url);
    const path = url.pathname;

    // Health probe from Telegram or monitoring
    if (request.method === "GET" && path === "/health") {
      const primaryOk = await checkHealth(env.CF_PRIMARY_URL, 3000);
      const backupOk  = await checkHealth(env.CF_BACKUP_URL,  3000);
      return new Response(
        JSON.stringify({ worker: "ok", primary: primaryOk, backup: backupOk }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }

    // Only handle POST to /webhook/<secret>
    if (request.method !== "POST" || !path.startsWith("/webhook/")) {
      return new Response("Not Found", { status: 404 });
    }

    // Verify secret
    const pathSecret = path.split("/webhook/")[1];
    if (pathSecret !== env.CF_WEBHOOK_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }

    // Determine target
    const primaryHealthy = await resolvePrimary(env);
    const targetBase     = primaryHealthy ? env.CF_PRIMARY_URL : env.CF_BACKUP_URL;

    try {
      const res = await forwardRequest(targetBase, path, request, env.CF_WEBHOOK_SECRET);
      // If primary returned an error, mark it unhealthy and try backup
      if (!res.ok && primaryHealthy) {
        _primaryHealthy  = false;
        _lastHealthCheck = Date.now();
        const backupRes  = await forwardRequest(
          env.CF_BACKUP_URL, path, request, env.CF_WEBHOOK_SECRET
        );
        return new Response(await backupRes.text(), {
          status:  backupRes.status,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(await res.text(), {
        status:  res.status,
        headers: { "Content-Type": "application/json" },
      });
    } catch (err) {
      // Primary timed out / network error — try backup
      if (primaryHealthy) {
        _primaryHealthy  = false;
        _lastHealthCheck = Date.now();
        try {
          const backupRes = await forwardRequest(
            env.CF_BACKUP_URL, path, request, env.CF_WEBHOOK_SECRET
          );
          return new Response(await backupRes.text(), {
            status:  backupRes.status,
            headers: { "Content-Type": "application/json" },
          });
        } catch (backupErr) {
          return new Response(JSON.stringify({ error: "Both upstreams failed" }), {
            status: 502,
            headers: { "Content-Type": "application/json" },
          });
        }
      }
      return new Response(JSON.stringify({ error: String(err) }), { status: 502 });
    }
  },
};
