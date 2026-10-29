// Outbound fetches for providers. Limits: https only, no redirects, a time limit, and a byte limit.
// Workers cannot pin the resolved IP address, so feed addresses come from the operator's secrets, never from users.

export class ProviderError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.code = code;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export async function boundedText(url: string, fetcher: FetchLike, maxBytes: number, timeoutMs: number): Promise<string> {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new ProviderError("bad_url");
  }
  if (parsed.protocol !== "https:" || parsed.username || parsed.password) throw new ProviderError("bad_url");
  if (parsed.hostname === "localhost" || /^[\d.]+$/.test(parsed.hostname) || parsed.hostname.includes(":")) {
    throw new ProviderError("bad_url");
  }
  let response: Response;
  try {
    response = await fetcher(url, { redirect: "manual", signal: AbortSignal.timeout(timeoutMs), headers: { Accept: "*/*" } });
  } catch {
    throw new ProviderError("unreachable");
  }
  if (response.status >= 300 && response.status < 400) throw new ProviderError("redirect_refused");
  if (!response.ok) throw new ProviderError(`http_${response.status}`);
  const declared = Number(response.headers.get("Content-Length") ?? "0");
  if (declared > maxBytes) throw new ProviderError("too_large");
  const body = response.body;
  if (!body) return "";
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel();
      throw new ProviderError("too_large");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}

export async function boundedJson(url: string, fetcher: FetchLike, maxBytes: number, timeoutMs: number): Promise<unknown> {
  const text = await boundedText(url, fetcher, maxBytes, timeoutMs);
  try {
    return JSON.parse(text);
  } catch {
    throw new ProviderError("bad_response");
  }
}
