// Typed client for the Life Easy API.
// The access token lives only in memory. The refresh token is kept in localStorage so a reload
// keeps you signed in; every storage access is wrapped because storage can be blocked.

import type {
  Application,
  ApplicationStatus,
  Approval,
  ChannelIdentity,
  ChatMessage,
  ChatResponse,
  Connection,
  FollowUp,
  Interview,
  Job,
  JobSummary,
  LinkCode,
  Match,
  MatchStatus,
  Page,
  Profile,
  Resume,
  Stats,
  TailorResult,
  TokenPair,
  User,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const REFRESH_KEY = "lifeeasy.refresh";

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;
const listeners = new Set<(signedIn: boolean) => void>();

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

function readRefresh(): string | null {
  try {
    return window.localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

function writeRefresh(value: string | null): void {
  try {
    if (value) window.localStorage.setItem(REFRESH_KEY, value);
    else window.localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* storage blocked: the session just won't survive a reload */
  }
}

function setTokens(tokens: TokenPair | null): void {
  accessToken = tokens?.access_token ?? null;
  writeRefresh(tokens?.refresh_token ?? null);
  listeners.forEach((fn) => fn(Boolean(accessToken)));
}

export function onAuthChange(fn: (signedIn: boolean) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function isSignedIn(): boolean {
  return Boolean(accessToken);
}

async function parseError(resp: Response): Promise<ApiError> {
  let code = `http_${resp.status}`;
  let message = resp.statusText || "Request failed";
  try {
    const data = await resp.json();
    if (data?.error) {
      code = data.error.code ?? code;
      message = data.error.message ?? message;
    } else if (typeof data?.detail === "string") {
      message = data.detail;
    } else if (Array.isArray(data?.detail)) {
      message = data.detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
    }
  } catch {
    /* not JSON */
  }
  return new ApiError(resp.status, code, message);
}

export async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  const token = readRefresh();
  if (!token) return false;
  refreshInFlight = (async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!resp.ok) {
        setTokens(null);
        return false;
      }
      setTokens((await resp.json()) as TokenPair);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

type Body = BodyInit | Record<string, unknown> | unknown[] | undefined;

async function raw(path: string, init: { method?: string; body?: Body; retry?: boolean } = {}): Promise<Response> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (init.body instanceof FormData || typeof init.body === "string" || init.body instanceof Blob) {
    body = init.body;
  } else if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.body);
  }
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const resp = await fetch(`${API_BASE}${path}`, { method: init.method ?? "GET", headers, body });
  if (resp.status === 401 && init.retry !== false && (await refreshSession())) {
    return raw(path, { ...init, retry: false });
  }
  if (!resp.ok) throw await parseError(resp);
  return resp;
}

async function json<T>(path: string, init: { method?: string; body?: Body } = {}): Promise<T> {
  const resp = await raw(path, init);
  const text = resp.status === 204 ? "" : await resp.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  // --- auth
  async login(email: string, password: string): Promise<void> {
    setTokens(await json<TokenPair>("/api/v1/auth/login", { method: "POST", body: { email, password } }));
  },
  async register(email: string, password: string, display_name: string): Promise<void> {
    setTokens(await json<TokenPair>("/api/v1/auth/register", { method: "POST", body: { email, password, display_name: display_name || null } }));
  },
  async logout(): Promise<void> {
    const token = readRefresh();
    setTokens(null);
    if (token) await fetch(`${API_BASE}/api/v1/auth/logout`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: token }) }).catch(() => undefined);
  },
  me: () => json<User>("/api/v1/auth/me"),

  // --- profile & account
  profile: () => json<Profile>("/api/v1/me/profile"),
  updateProfile: (patch: Partial<Profile> & { display_name?: string }) => json<Profile>("/api/v1/me/profile", { method: "PATCH", body: patch }),
  exportData: () => json<Record<string, unknown>>("/api/v1/me/export"),
  async deleteAccount(): Promise<void> {
    await json("/api/v1/me", { method: "DELETE" });
    setTokens(null);
  },

  // --- chat
  chatHistory: () => json<ChatMessage[]>("/api/v1/chat/messages?limit=100"),
  chat: (text: string) => json<ChatResponse>("/api/v1/chat/messages", { method: "POST", body: { text } }),
  notifications: () => json<ChatMessage[]>("/api/v1/chat/notifications"),

  // --- jobs & matches
  jobs: (p: { query?: string; location?: string; remote?: boolean | null; limit?: number; offset?: number }) =>
    json<Page<JobSummary>>(`/api/v1/jobs${qs(p)}`),
  job: (id: string) => json<Job>(`/api/v1/jobs/${id}`),
  ingest: () => json<{ status: string }>("/api/v1/jobs/ingest", { method: "POST", body: {} }),
  matches: (status?: MatchStatus) => json<Match[]>(`/api/v1/matches${qs({ status })}`),
  refreshMatches: () => json<{ status: string }>("/api/v1/matches/refresh", { method: "POST" }),
  setMatch: (jobId: string, status: MatchStatus) => json<Match>(`/api/v1/matches/${jobId}`, { method: "PATCH", body: { status } }),

  // --- tracker
  applications: (status?: string) => json<Page<Application>>(`/api/v1/applications${qs({ status, limit: 200 })}`),
  stats: () => json<Stats>("/api/v1/applications/stats"),
  addApplication: (body: { company: string; title: string; status: ApplicationStatus; source_url?: string; notes?: string }) =>
    json<Application>("/api/v1/applications", { method: "POST", body }),
  updateApplication: (id: string, body: { status?: ApplicationStatus; note?: string; notes?: string }) =>
    json<Application>(`/api/v1/applications/${id}`, { method: "PATCH", body }),
  deleteApplication: (id: string) => json<void>(`/api/v1/applications/${id}`, { method: "DELETE" }),
  interviews: () => json<Interview[]>("/api/v1/interviews"),
  addInterview: (appId: string, body: { scheduled_at: string; kind: string; location?: string }) =>
    json<Interview>(`/api/v1/applications/${appId}/interviews`, { method: "POST", body }),
  followUps: () => json<FollowUp[]>("/api/v1/follow-ups"),

  // --- approvals
  approvals: (status?: string) => json<Approval[]>(`/api/v1/approvals${qs({ status })}`),
  approve: (a: Approval) => json<Approval>(`/api/v1/approvals/${a.id}/approve`, { method: "POST", body: { content_hash: a.content_hash } }),
  reject: (id: string) => json<Approval>(`/api/v1/approvals/${id}/reject`, { method: "POST", body: {} }),
  editApproval: (id: string, body: { body: string; subject?: string | null }) => json<Approval>(`/api/v1/approvals/${id}/edit`, { method: "POST", body }),

  // --- resumes
  resumes: () => json<Resume[]>("/api/v1/resumes"),
  uploadResume(file: File) {
    const form = new FormData();
    form.append("file", file);
    return json<Resume>("/api/v1/resumes", { method: "POST", body: form });
  },
  setPrimaryResume: (id: string) => json<Resume>(`/api/v1/resumes/${id}/primary`, { method: "POST" }),
  deleteResume: (id: string) => json<void>(`/api/v1/resumes/${id}`, { method: "DELETE" }),
  downloadResume: async (id: string) => (await raw(`/api/v1/resumes/${id}/download`)).blob(),
  tailor: (job_id: string) => json<TailorResult>("/api/v1/resumes/tailor", { method: "POST", body: { job_id } }),

  // --- connections & channels
  connections: () => json<Connection[]>("/api/v1/email/connections"),
  oauthStart: (provider: "google" | "microsoft" | "linkedin") => json<{ url: string }>(`/api/v1/connections/oauth/${provider}/start`),
  addImap: (body: { account_email: string; username?: string; password: string; imap_host: string; imap_port: number; smtp_host: string; smtp_port: number }) =>
    json<Connection>("/api/v1/email/connections/imap", { method: "POST", body }),
  removeConnection: (id: string) => json<void>(`/api/v1/email/connections/${id}`, { method: "DELETE" }),
  linkCode: () => json<LinkCode>("/api/v1/channels/link-code", { method: "POST" }),
  channels: () => json<ChannelIdentity[]>("/api/v1/channels"),
  unlinkChannel: (id: string) => json<void>(`/api/v1/channels/${id}`, { method: "DELETE" }),
};

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}
