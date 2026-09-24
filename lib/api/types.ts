/**
 * Shared request/response types for the CycloAI backend API.
 *
 * These types mirror what the FastAPI routes actually return
 * (backend/src/cycloai/api/routes_*.py). They are hand-written; codegen is
 * deferred until backend tooling supports it. When a backend route changes,
 * update the matching type here in the same change.
 *
 * Config note: the API base URL comes from `NEXT_PUBLIC_API_URL` and
 * defaults to `http://localhost:8000`. The backend must be running for any
 * call to succeed, and the frontend and backend share the session over an
 * httpOnly cookie (same site), which is why every request must be sent with
 * `credentials: "include"`.
 */

// ---------------------------------------------------------------------------
// Auth — routes_auth.py
// ---------------------------------------------------------------------------

/** The identity returned by successful register/login: id and email only. */
export interface AuthUser {
  id: string;
  email: string;
}

export interface AuthCredentials {
  email: string;
  password: string;
}

/** Generic `{ detail: string }` acknowledgement (logout, account deletion). */
export interface DetailAck {
  detail: string;
}

// ---------------------------------------------------------------------------
// Profile / onboarding — routes_profile.py (ProfileOut / ProfileUpdate)
// ---------------------------------------------------------------------------

export type TrainingSystem = "power" | "heart_rate";

/** The caller's own profile: the `profiles` columns plus their email. */
export interface Profile {
  id: string;
  /** The account email, joined from `users` — the only non-`profiles` field. */
  email: string;
  created_at: string;
  updated_at: string;
  display_name: string | null;
  avatar_url: string | null;
  strava_id: number | null;
  strava_connected: boolean;
  strava_connected_at: string | null;
  objective: string | null;
  weekly_hours: number | null;
  gym_days_per_week: number | null;
  injuries: string | null;
  has_power_meter: boolean;
  target_event: string | null;
  target_event_date: string | null;
  onboarding_completed: boolean;
  training_system: TrainingSystem;
  lthr_bpm: number | null;
  ftp_estimated: number | null;
  ctl: number | null;
  atl: number | null;
  tsb: number | null;
  weekly_volume_km: number | null;
  weekly_volume_hours: number | null;
  avg_days_per_week: number | null;
  last_sync_at: string | null;
}

/**
 * The fields an athlete may PATCH on their own profile. `onboarding_completed`
 * is NOT settable here — only `POST /onboarding/complete` can flip it, and
 * only after validating the required fields.
 */
export interface ProfileUpdate {
  display_name?: string | null;
  avatar_url?: string | null;
  objective?: string | null;
  weekly_hours?: number | null;
  gym_days_per_week?: number | null;
  injuries?: string | null;
  has_power_meter?: boolean | null;
  target_event?: string | null;
  target_event_date?: string | null;
  training_system?: TrainingSystem | null;
  lthr_bpm?: number | null;
  ftp_estimated?: number | null;
}

// ---------------------------------------------------------------------------
// Conversations and messages — routes_conversations.py
// ---------------------------------------------------------------------------

export type MessageRole = "user" | "assistant";

/** One conversation: exactly the `conversations` columns. */
export interface Conversation {
  id: string;
  created_at: string;
  updated_at: string;
  title: string | null;
  summary: string | null;
}

export interface ConversationCreate {
  title?: string | null;
}

/** One stored message: exactly the `messages` columns. */
export interface Message {
  id: string;
  conversation_id: string;
  user_id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  metadata: Record<string, unknown> | null;
}

export interface MessageCreate {
  role: MessageRole;
  content: string;
  metadata?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Chat — routes_chat.py (ChatContextOut)
// ---------------------------------------------------------------------------

/**
 * One chat turn's context (`POST /chat/context`): the assembled prompt, the
 * conversation id (created when absent) and whether knowledge was used.
 * Deliberately minimal — mirrors backend `ChatContextOut`.
 */
export interface ChatContextResponse {
  conversation_id: string;
  system_prompt: string;
  knowledge_used: boolean;
}

// ---------------------------------------------------------------------------
// Generation — routes_generate.py
// ---------------------------------------------------------------------------

/** The athlete's declared training system and its threshold. */
export interface Thresholds {
  system: TrainingSystem;
  ftp_watts?: number | null;
  lthr_bpm?: number | null;
}

/** The body of `POST /generate`. Body values win over stored profile values. */
export interface GenerateRequest {
  objective: string;
  thresholds: Thresholds;
  weekly_hours?: number | null;
  gym_days_per_week?: number | null;
  injuries?: string | null;
  target_event?: string | null;
  has_power_meter?: boolean | null;
  guidance?: string | null;
  ctl?: number | null;
  atl?: number | null;
  tsb?: number | null;
}

/** One validation-gate finding, with the layer it came from. */
export interface GenerationFinding {
  source: string;
  code: string;
  severity: string;
  message: string;
}

/** The 422 body: the gate refused the model output on every attempt. */
export interface GenerationRejected {
  findings: GenerationFinding[];
  attempts: number;
}

/** The 200 body: the validated workout plus the coach prose. */
export interface GenerationSuccess {
  workout: Record<string, unknown>;
  prose: string;
  knowledge_used: boolean;
  attempts: number;
  warnings: GenerationFinding[];
}

// ---------------------------------------------------------------------------
// Waitlist — routes_waitlist.py
// ---------------------------------------------------------------------------

export interface WaitlistSignup {
  email: string;
  source?: string | null;
}

// ---------------------------------------------------------------------------
// Error bodies
// ---------------------------------------------------------------------------

/** One FastAPI request-validation error item (the 422 `detail` array). */
export interface ApiValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/**
 * What an error response body carries. `HTTPException(detail=...)` errors
 * (and most routes) return a string; FastAPI request-validation errors
 * return the structured array — that shape is exactly what callers need on
 * a 422, so it is preserved rather than stringified away.
 */
export interface ApiErrorBody {
  detail: string | ApiValidationErrorItem[];
}
