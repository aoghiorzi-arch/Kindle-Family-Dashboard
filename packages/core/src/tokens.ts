// Random credentials. Only SHA-256 hashes are ever stored.

export const TOKEN_PREFIX = "kfd_";

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function randomSecret(byteLength = 32): string {
  return toBase64Url(crypto.getRandomValues(new Uint8Array(byteLength)));
}

export function generateApiToken(): string {
  return TOKEN_PREFIX + randomSecret(32);
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return toHex(new Uint8Array(digest));
}

export function isApiTokenShape(value: string): boolean {
  return value.startsWith(TOKEN_PREFIX) && value.length === TOKEN_PREFIX.length + 43;
}
