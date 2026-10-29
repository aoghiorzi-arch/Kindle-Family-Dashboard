// Cloudflare Worker entry point. Routes requests and turns errors into the standard error shape.
import type { Env } from "./env.ts";
import { errorResponse, HttpError, json } from "./http.ts";
import * as h from "./handlers.ts";
import { accessConfigured } from "./auth.ts";
import { runScheduled } from "./scheduled.ts";

type Route = {
  method: string;
  pattern: RegExp;
  run: (request: Request, env: Env, now: Date, url: URL, params: string[]) => Promise<Response>;
};

const ROUTES: Route[] = [
  {
    method: "GET",
    pattern: /^\/api\/health$/,
    // Configuration only: says whether browser sign-in is available, never any household data.
    run: async (_req, env) => json({
      ok: true,
      signIn: accessConfigured(env) ? "cloudflare-access" : env.ENVIRONMENT === "local" ? "development" : "unavailable",
    }),
  },
  { method: "GET", pattern: /^\/api\/me$/, run: (req, env, now) => h.me(req, env, now) },
  { method: "POST", pattern: /^\/api\/dev\/login$/, run: (req, env, now) => h.devLogin(req, env, now) },
  { method: "POST", pattern: /^\/api\/logout$/, run: (req, env, now) => h.logout(req, env, now) },
  { method: "GET", pattern: /^\/api\/shopping$/, run: (req, env, now) => h.listShopping(req, env, now) },
  { method: "POST", pattern: /^\/api\/shopping$/, run: (req, env, now) => h.createItem(req, env, now) },
  {
    method: "PATCH",
    pattern: /^\/api\/shopping\/([^/]+)$/,
    run: (req, env, now, _url, [id]) => h.updateItem(req, env, now, id),
  },
  {
    method: "DELETE",
    pattern: /^\/api\/shopping\/([^/]+)$/,
    run: (req, env, now, url, [id]) => h.deleteItem(req, env, now, id, url),
  },
  { method: "GET", pattern: /^\/api\/device\/snapshot$/, run: (req, env, now) => h.deviceSnapshot(req, env, now) },
  { method: "GET", pattern: /^\/api\/snapshot\/preview$/, run: (req, env, now) => h.snapshotPreview(req, env, now) },
  { method: "GET", pattern: /^\/api\/admin\/devices$/, run: (req, env, now) => h.listDevices(req, env, now) },
  { method: "GET", pattern: /^\/api\/admin\/household\/location$/, run: (req, env, now) => h.getLocation(req, env, now) },
  { method: "PUT", pattern: /^\/api\/admin\/household\/location$/, run: (req, env, now) => h.setLocation(req, env, now) },
  { method: "GET", pattern: /^\/api\/admin\/members$/, run: (req, env, now) => h.listMembers(req, env, now) },
  { method: "POST", pattern: /^\/api\/admin\/members$/, run: (req, env, now) => h.inviteMember(req, env, now) },
  // Shortcuts use this path. It is outside the browser sign-in and authenticated by its own token only.
  { method: "POST", pattern: /^\/api\/shortcut\/shopping$/, run: (req, env, now) => h.createItem(req, env, now) },
  { method: "POST", pattern: /^\/api\/admin\/devices$/, run: (req, env, now) => h.createDevice(req, env, now) },
  {
    method: "POST",
    pattern: /^\/api\/admin\/devices\/([^/]+)\/rotate$/,
    run: (req, env, now, _url, [id]) => h.rotateDevice(req, env, now, id),
  },
  {
    method: "DELETE",
    pattern: /^\/api\/admin\/devices\/([^/]+)$/,
    run: (req, env, now, _url, [id]) => h.revokeDevice(req, env, now, id),
  },
];

export async function handle(request: Request, env: Env, now: Date = new Date()): Promise<Response> {
  const url = new URL(request.url);
  try {
    let pathMatched = false;
    for (const route of ROUTES) {
      const match = route.pattern.exec(url.pathname);
      if (!match) continue;
      pathMatched = true;
      if (route.method !== request.method) continue;
      return await route.run(request, env, now, url, match.slice(1));
    }
    if (pathMatched) throw new HttpError(405, "method_not_allowed", "Method not allowed");
    throw new HttpError(404, "not_found", "Not found");
  } catch (error) {
    if (error instanceof HttpError) return errorResponse(error);
    // Never return internal details: they can contain request or database text.
    console.error("unhandled error", error instanceof Error ? error.name : "unknown");
    return errorResponse(new HttpError(500, "internal", "Something went wrong"));
  }
}

// Cron entry point: refreshes provider caches. Failures are logged by error name only.
export async function scheduledJob(env: Env, now: Date = new Date()): Promise<void> {
  try {
    await runScheduled(env, now);
  } catch (error) {
    console.error("scheduled job failed", error instanceof Error ? error.name : "unknown");
  }
}

export default {
  fetch: (request: Request, env: Env) => handle(request, env),
  scheduled: (_controller: unknown, env: Env, ctx: { waitUntil(promise: Promise<unknown>): void }) => {
    ctx.waitUntil(scheduledJob(env));
  },
};
