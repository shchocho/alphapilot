/** 백엔드 API 호출. 세션 쿠키는 브라우저가 붙이고, 상태를 바꾸는 요청에는 CSRF 토큰 헤더를 붙인다. */

export class ApiError extends Error {
  status: number;
  code: string;
  extra: Record<string, unknown>;

  constructor(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }

  get needsStepUp(): boolean {
    return this.code === "stepup_required";
  }
}

let csrfToken = "";
let onUnauthenticated: (() => void) | null = null;

export function setCsrf(token: string | null | undefined): void {
  csrfToken = token ?? "";
}

export function setUnauthenticatedHandler(handler: () => void): void {
  onUnauthenticated = handler;
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["x-csrf-token"] = csrfToken;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "network", "서버에 연결하지 못했습니다. 네트워크를 확인한 뒤 다시 시도하세요");
  }
  if (response.ok) {
    const type = response.headers.get("content-type") ?? "";
    return (type.includes("application/json") ? await response.json() : await response.text()) as T;
  }
  let code = "http";
  let message = `요청을 처리하지 못했습니다(${response.status})`;
  let extra: Record<string, unknown> = {};
  try {
    const data = await response.json();
    if (data?.error) {
      ({ code = code, message = message, ...extra } = data.error);
    }
  } catch {
    /* 본문이 JSON이 아니면 기본 문구를 쓴다 */
  }
  if (response.status === 401 && code === "not_authenticated") onUnauthenticated?.();
  throw new ApiError(response.status, code, message, extra);
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body: unknown = {}) => request<T>("POST", url, body),
  put: <T>(url: string, body: unknown) => request<T>("PUT", url, body),
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "알 수 없는 오류가 발생했습니다";
}
