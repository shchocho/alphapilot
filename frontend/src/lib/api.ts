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

/** GitHub Pages 데모(vite build --mode demo): 서버 없이 미리 저장한 응답(public/demo/*.json)만 읽는다. */
export const DEMO = import.meta.env.MODE === "demo";

/** backend/scripts/export_demo.py의 key()와 같은 규칙. */
export const demoKey = (url: string) => url.replace(/^\/api\//, "").replace(/[^A-Za-z0-9-]/g, "_");

// 데모 로그인 상태. 새로 고쳐도 유지되게 sessionStorage에 두되, 못 쓰면 이 탭 메모리로만 기억한다.
let demoAuthed = (() => {
  try {
    return sessionStorage.getItem("ap-demo-auth") === "1";
  } catch {
    return false;
  }
})();

function setDemoAuthed(value: boolean): void {
  demoAuthed = value;
  try {
    sessionStorage.setItem("ap-demo-auth", value ? "1" : "");
  } catch {
    /* 저장하지 못해도 이 탭에서는 유지된다 */
  }
}

async function demoRequest<T>(method: string, url: string): Promise<T> {
  if (url === "/api/auth/state") {
    return { setup: "done", authenticated: demoAuthed, csrf: demoAuthed ? "demo" : null, elevated: demoAuthed, setup_token_required: false } as T;
  }
  if (url === "/api/auth/login" || url === "/api/auth/logout") {
    setDemoAuthed(url === "/api/auth/login");
    return { csrf: "demo" } as T;
  }
  if (url === "/api/auth/account") return { username: "demo", recovery_codes_left: 10 } as T;
  if (url === "/api/settings/broker/keys") return { mock: null, live: null } as T;
  if (method !== "GET") throw new ApiError(403, "demo", "데모 화면이라 바꿀 수 없습니다. 내 PC에서 실행하면 쓸 수 있습니다");
  const search = /^\/api\/stocks\/search\?q=(.*)$/.exec(url);
  const response = await fetch(`${import.meta.env.BASE_URL}demo/${demoKey(search ? "/api/stocks/_all" : url)}.json`).catch(() => null);
  if (!response?.ok) throw new ApiError(404, "demo", "데모에 저장되지 않은 화면입니다");
  const data = await response.json();
  if (!search) return data as T;
  const q = decodeURIComponent(search[1]).trim().toLowerCase();
  const results = (data as { code: string; name: string }[]).filter((s) => s.name.toLowerCase().includes(q) || s.code.startsWith(q));
  return { results: results.slice(0, 12) } as T;
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  if (DEMO) return demoRequest<T>(method, url);
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
  delete: <T>(url: string) => request<T>("DELETE", url),
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "알 수 없는 오류가 발생했습니다";
}
