/**
 * OrderHub CRM — IdlaserDraftJob Types (S004-mcp-wrapper)
 *
 * Hand-written mirror of backend/schemas/idlaser_draft_job.py. Per OQ-D
 * we use manual TypeScript types rather than codegen — keep this file in
 * sync with the Pydantic schemas. Drift risk is documented in CLAUDE.md.
 */

export type DraftJobState =
  | 'pending'
  | 'running'
  | 'review_required'
  | 'reprocessing'
  | 'ready'
  | 'failed'
  | 'cancelled'
  | 'connecting'
  | 'idle';

// Server-side states (subset of DraftJobState; the latter adds two
// client-only states: 'connecting' and 'idle' for the hook's UX).
export type ServerJobState =
  | 'pending'
  | 'running'
  | 'needs_review'
  | 'ready'
  | 'failed'
  | 'cancelled';

export interface DraftJobStatusResponse {
  id: string;
  state: ServerJobState;
  result_attachment_id: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface DraftEventPayload {
  payload: Record<string, unknown>;
  timestamp: string;
  job_state: ServerJobState;
}

export interface DraftEvent {
  type: string; // 'job.started' | 'detect.classical.completed' | …
  payload: Record<string, unknown>;
  timestamp: string;
  job_state: ServerJobState;
}

export interface ReviewContext {
  bestGuessCorners: number[][]; // 4 × [x, y] in original-photo px
  rectifiedPreviewUrl: string | null;
  reason: string;
}

export interface ManualCornersBody {
  corners: number[][];
}
