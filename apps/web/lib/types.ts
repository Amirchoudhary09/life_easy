// Shapes returned by the Life Easy API (apps/api). Keep in sync with the Pydantic schemas.

export type UUID = string;

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: UUID;
  email: string;
  display_name: string | null;
  created_at: string;
}

export interface Preferences {
  locations: string[];
  remote: "any" | "remote" | "onsite" | "hybrid";
  employment_types: string[];
  titles: string[];
  salary_min: number | null;
  currency: string;
  exclude_companies: string[];
  digest_hour_local: number;
}

export interface Profile {
  headline: string | null;
  summary: string | null;
  location: string | null;
  experience_years: number | null;
  skills: string[];
  preferences: Partial<Preferences>;
  timezone: string;
  digest_enabled: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobSummary {
  id: UUID;
  source: string;
  company: string;
  title: string;
  location: string | null;
  remote: boolean | null;
  employment_type: string | null;
  salary_text: string | null;
  apply_url: string;
  posted_at: string | null;
}

export interface Job extends JobSummary {
  source_url: string | null;
  fetched_at: string;
  description: string | null;
}

export interface MatchExplanation {
  summary?: string;
  strengths?: string[];
  gaps?: string[];
  location_ok?: boolean;
  recommended?: boolean;
  [key: string]: unknown;
}

export type MatchStatus = "suggested" | "saved" | "skipped" | "applied";

export interface Match {
  job: JobSummary;
  score: number;
  explanation: MatchExplanation;
  status: MatchStatus;
  updated_at: string;
}

export const APPLICATION_STATUSES = [
  "planned",
  "applied",
  "screening",
  "interview",
  "offer",
  "accepted",
  "rejected",
  "withdrawn",
] as const;
export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export interface Application {
  id: UUID;
  job_id: UUID | null;
  company: string;
  title: string;
  status: ApplicationStatus;
  source_url: string | null;
  applied_at: string | null;
  next_follow_up_at: string | null;
  last_contact_at: string | null;
  notes: string | null;
  resume_id: UUID | null;
  created_at: string;
  updated_at: string;
}

export interface Interview {
  id: UUID;
  application_id: UUID;
  scheduled_at: string;
  kind: string;
  location: string | null;
  notes: string | null;
  prep_sent_at: string | null;
  outcome: string | null;
}

export interface FollowUp {
  id: UUID;
  application_id: UUID;
  due_at: string;
  status: string;
  approval_id: UUID | null;
}

export interface Stats {
  by_status: Record<string, number>;
  applied_last_7_days: number;
  interviews_upcoming: number;
  follow_ups_due: number;
}

export type ApprovalStatus = "pending" | "approved" | "rejected" | "executing" | "executed" | "failed" | "expired";

export interface Approval {
  id: UUID;
  action_type: string;
  channel: string;
  destination: { from?: string; to?: string[]; cc?: string[]; audience?: string; recipient?: string };
  subject: string | null;
  body: string;
  attachments: { type?: string; filename?: string; resume_id?: string }[];
  content_hash: string;
  status: ApprovalStatus;
  preview_channel: string | null;
  expires_at: string;
  approved_at: string | null;
  executed_at: string | null;
  result: Record<string, unknown>;
  error: string | null;
  related_application_id: UUID | null;
  created_at: string;
}

export interface Resume {
  id: UUID;
  filename: string;
  content_type: string;
  size_bytes: number;
  is_primary: boolean;
  parsed: Record<string, unknown>;
  tailored_for_job_id: UUID | null;
  has_text: boolean;
  created_at: string;
}

export interface TailorResult {
  resume: Resume;
  markdown: string;
  ats: { matched_keywords?: string[]; missing_keywords?: string[]; score?: number; notes?: string[] };
}

export interface Connection {
  id: UUID;
  provider: "google" | "microsoft" | "imap" | "linkedin" | string;
  account_email: string;
  scopes: string[];
  revoked_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface ChannelIdentity {
  id: UUID;
  provider: "whatsapp" | "telegram" | string;
  display_name: string | null;
  external_id_hint: string;
  verified_at: string;
}

export interface LinkCode {
  code: string;
  expires_at: string;
  instructions: string;
  channels: { whatsapp: boolean; telegram: boolean };
}

export interface ChatMessage {
  id: UUID;
  role: "user" | "assistant" | "tool";
  content: string;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface ChatResponse {
  reply: string;
  approvals: Approval[];
  tool_calls: string[];
}
