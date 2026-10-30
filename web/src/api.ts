export class ApiError extends Error {
  status: number;
  fields: unknown;
  requestId?: string;
  constructor(
    status: number,
    message: string,
    fields: unknown = {},
    requestId?: string,
  ) {
    super(message);
    this.status = status;
    this.fields = fields;
    this.requestId = requestId;
  }
}

export async function api<T>(
  path: string,
  options: {
    organizationId?: string;
    signal?: AbortSignal;
    body?: unknown;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.organizationId)
    headers["X-Organization-ID"] = options.organizationId;
  if (options.body !== undefined) {
    const csrf = await api<{ csrf_token: string }>("/auth/csrf/");
    headers["Content-Type"] = "application/json";
    headers["X-CSRFToken"] = csrf.csrf_token;
  }
  const response = await fetch(`/api/v1${path}`, {
    method: options.body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers,
    signal: options.signal,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (response.status === 204) return undefined as T;
  const json = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) {
      window.dispatchEvent(new Event("clearance-session-expired"));
    }
    throw new ApiError(
      response.status,
      json?.error?.message || "The request could not be completed.",
      json?.error?.fields,
      json?.request_id,
    );
  }
  if (json === null)
    throw new Error(
      "The server returned an unreadable response. Please retry.",
    );
  return json as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "The connection could not be confirmed. Refresh the records before retrying a saved change.";
}

export function fieldMessages(fields: unknown, prefix = ""): string[] {
  if (Array.isArray(fields))
    return fields.flatMap((value) => fieldMessages(value, prefix));
  if (typeof fields === "object" && fields !== null) {
    return Object.entries(fields).flatMap(([key, value]) =>
      fieldMessages(value, key.replaceAll("_", " ")),
    );
  }
  return fields == null
    ? []
    : [`${prefix ? `${prefix}: ` : ""}${String(fields)}`];
}
