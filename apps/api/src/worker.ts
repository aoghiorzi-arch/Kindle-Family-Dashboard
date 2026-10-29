// Cloudflare Worker entry point. Routes requests and turns errors into the standard error shape.
import type { Env } from "./env.ts";
import { errorResponse, HttpError, json } from "./http.ts";
import * as h from "./handlers.ts";

type Route = {
  method: string;
  pattern: RegExp;
  run: (request: Request, env: Env, now: Date, url: URL, params: string[]) => Promise<Response>;
};

const ROUTES: Route[] = [
  { method: "GET", pattern: /^\/api\/health$/, run: async () => json({ ok: true }) },
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

export default {
  fetch: (request: Request, env: Env) => handle(request, env),
};
