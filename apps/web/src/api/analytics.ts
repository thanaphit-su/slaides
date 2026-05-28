import { api, apiBlob } from "./client";

export interface TranscriptEvent {
  occurred_at: string;
  event_type: string;
  payload: Record<string, unknown>;
  source: string;
}

export interface TranscriptResponse {
  session_id: string;
  deck_id: string;
  started_at: string;
  ended_at: string | null;
  events: TranscriptEvent[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  per_slide: SlideSummary[];
  per_participant: ParticipantSummary[];
  pre_migration_warning?: string | null;
}

export interface SlideSummary {
  slide_id: string;
  kind: "deck" | "session";
  interaction_count: number;
  by_kind: Record<string, number>;
}

export interface ParticipantSummary {
  participant_ref: string;
  display_name: string;
  anon: boolean;
  joined_at: string;
  total_interactions: number;
  by_kind: Record<string, number>;
}

export interface ReplayResponse {
  session_id: string;
  events: TranscriptEvent[];
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}

export const analyticsApi = {
  replay: (sessionId: string, limit = 500, offset = 0) =>
    api<ReplayResponse>(`/sessions/${sessionId}/replay?limit=${limit}&offset=${offset}`),

  transcript: (sessionId: string) =>
    api<TranscriptResponse>(`/sessions/${sessionId}/transcript`),

  downloadTranscriptCsv: async (sessionId: string) => {
    const blob = await apiBlob(`/sessions/${sessionId}/transcript.csv`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `session-${sessionId}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  },

  downloadTranscriptJson: async (sessionId: string) => {
    const blob = await apiBlob(`/sessions/${sessionId}/transcript.json`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `session-${sessionId}.slaides.json`;
    link.click();
    URL.revokeObjectURL(url);
  },
};
