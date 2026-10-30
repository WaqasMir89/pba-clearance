import { ApiError } from "./api";
import type { FilingPayload } from "./types";

export type PendingStage = {
  version: 1;
  cycle_id: string;
  source_filename: string;
  source_sha256: string;
  idempotency_key: string;
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const digest = /^[0-9a-f]{64}$/;

export function recoveryKey(userId: string, organizationId: string) {
  return `clearance:intake:${userId}:${organizationId}`;
}

function readRecord(key: string): Record<string, unknown> | null {
  try {
    const text = sessionStorage.getItem(key);
    if (!text) return null;
    const value: unknown = JSON.parse(text);
    if (typeof value !== "object" || value === null || Array.isArray(value))
      throw new Error();
    return value as Record<string, unknown>;
  } catch {
    throw new ApiError(
      0,
      "The saved recovery record could not be read. Keep this tab open and restore session storage before submitting.",
    );
  }
}

export function readStage(key: string): PendingStage | null {
  const value = readRecord(key);
  if (!value) return null;
  if (
    value.version !== 1 ||
    typeof value.cycle_id !== "string" ||
    !uuid.test(value.cycle_id) ||
    typeof value.source_filename !== "string" ||
    typeof value.source_sha256 !== "string" ||
    !digest.test(value.source_sha256) ||
    typeof value.idempotency_key !== "string" ||
    !uuid.test(value.idempotency_key)
  ) {
    throw new ApiError(
      0,
      "The saved upload recovery record needs review before another upload.",
    );
  }
  return value as PendingStage;
}

export function readFiling(key: string): FilingPayload | null {
  const value = readRecord(key);
  if (!value) return null;
  if (
    typeof value.expected_preview_hash !== "string" ||
    !digest.test(value.expected_preview_hash) ||
    typeof value.simulation_at !== "string" ||
    !Number.isFinite(Date.parse(value.simulation_at)) ||
    typeof value.declaration_version !== "string" ||
    value.declaration_accepted !== true ||
    typeof value.idempotency_key !== "string" ||
    !uuid.test(value.idempotency_key)
  ) {
    throw new ApiError(
      0,
      "The saved filing recovery record needs review before another filing.",
    );
  }
  return value as FilingPayload;
}

export function remember(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    throw new ApiError(
      0,
      "Recovery could not be saved in this tab. Enable session storage before submitting.",
    );
  }
}

export function forget(key: string) {
  sessionStorage.removeItem(key);
}

export async function sha256(bytes: ArrayBuffer | Uint8Array) {
  const content =
    bytes instanceof Uint8Array ? new Uint8Array(bytes).buffer : bytes;
  const hash = await crypto.subtle.digest("SHA-256", content);
  return Array.from(new Uint8Array(hash), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

export function base64(bytes: Uint8Array) {
  let text = "";
  for (let offset = 0; offset < bytes.length; offset += 16384) {
    text += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  }
  return btoa(text);
}

export function downloadText(text: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  // Give the browser time to begin the download before releasing the in-memory URL.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function definiteRejection(error: unknown) {
  return (
    error instanceof ApiError &&
    error.status >= 400 &&
    error.status < 500 &&
    error.status !== 408 &&
    error.status !== 429
  );
}
