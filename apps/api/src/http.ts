// Response helpers. Errors use one shape and never echo request data or secrets.

export class HttpError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const SECURITY_HEADERS: Record<string, string> = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
  "Referrer-Policy": "no-referrer",
};

export function json(body: unknown, status = 200, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...SECURITY_HEADERS, ...extra },
  });
}

export function errorResponse(error: HttpError): Response {
  return json({ error: { code: error.code, message: error.message } }, error.status);
}

const MAX_BODY_BYTES = 4096;

export async function readJson(request: Request): Promise<Record<string, unknown>> {
  const type = request.headers.get("Content-Type") ?? "";
  if (!type.toLowerCase().startsWith("application/json")) {
    throw new HttpError(415, "unsupported_media_type", "Send application/json");
  }
  const length = Number(request.headers.get("Content-Length") ?? "0");
  if (length > MAX_BODY_BYTES) throw new HttpError(413, "too_large", "Request body is too large");
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_BODY_BYTES) {
    throw new HttpError(413, "too_large", "Request body is too large");
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new HttpError(400, "invalid_body", "Body must be a JSON object");
    }
    return parsed as Record<string, unknown>;
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(400, "invalid_json", "Body is not valid JSON");
  }
}
