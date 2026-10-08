const TOKEN_KEY = "sc_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string | null) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    setToken(null);
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      const d = body.detail;
      msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((e: any) => e.msg).join("; ") : msg;
    } catch {}
    throw new ApiError(res.status, msg);
  }
  return res;
}

export async function api<T = any>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await request(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return res.status === 204 ? (undefined as T) : res.json();
}

export async function login(username: string, password: string) {
  const res = await request("/auth/login", {
    method: "POST",
    body: new URLSearchParams({ username, password }),
  });
  return res.json();
}

export async function downloadPdf(path: string) {
  const res = await request(path);
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] || "report.pdf";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
