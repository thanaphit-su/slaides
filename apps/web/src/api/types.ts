export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  approval_status: ApprovalStatus;
}

export interface AuthResponse {
  access: string;
  refresh: string;
  user: User;
}

export interface Section {
  id: string;
  title: string;
  position: number;
}

export interface SlideWidgetEmbed {
  placement_id: string;
  widget_id: string;
  revision_id: string | null;
  revision?: WidgetRevision | null;
  kind: string;
  name: string;
  props: Record<string, unknown>;
}

export interface Slide {
  id: string;
  deck_id: string;
  section_id: string | null;
  position: number;
  kicker: string | null;
  markdown: string;
  updated_at: string;
  widgets: SlideWidgetEmbed[];
}

export interface WidgetBehavior {
  kind: "quiet" | "loud";
  aggregator?: "tally" | "latest_per_participant" | "append" | "set_union" | "keyed_tally";
  contribution_schema?: Record<string, unknown>;
}

/** Widgets v2 Step 4 — late-joiner snapshot entry + the canonical
 * `widget.state` payload shape. Carries one Loud iframe widget's current
 * aggregated state. */
export interface PlacementState {
  placement_id: string;
  widget_id: string | null;
  aggregator: string;
  state: Record<string, unknown>;
  state_version: number;
  closed: boolean;
}

export interface Widget {
  id: string;
  deck_id: string;
  derived_from_id: string | null;
  name: string;
  kind: string;
  description: string | null;
  html: string;
  js: string | null;
  css: string | null;
  props_schema: Record<string, unknown>;
  tags: string[];
  version: string;
  behavior: WidgetBehavior;
  current_revision_id?: string | null;
  example_props?: Record<string, unknown>;
  ai_spec?: Record<string, unknown>;
}

export interface WidgetAiMessage {
  id: string;
  thread_id: string;
  role: string;
  message_type: string;
  content: Record<string, unknown>;
  revision_id: string | null;
}

export interface WidgetAiThread {
  id: string;
  widget_id: string;
  title: string | null;
  compact_summary: Record<string, unknown>;
  messages: WidgetAiMessage[];
}

export interface WidgetRevision {
  id: string;
  widget_id: string;
  version_number: number;
  html: string;
  js: string | null;
  css: string | null;
  props_schema: Record<string, unknown>;
  example_props: Record<string, unknown>;
  behavior: WidgetBehavior;
  ai_spec: Record<string, unknown>;
  created_reason: string | null;
}

export interface WidgetSummary {
  id: string;
  deck_id: string;
  derived_from_id: string | null;
  name: string;
  kind: string;
  description: string | null;
  tags: string[];
  version: string;
  behavior: WidgetBehavior;
}

export interface Deck {
  id: string;
  title: string;
  subtitle: string | null;
  cover: string | null;
  manifest: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  sections: Section[];
  slides: Slide[];
}

export interface DeckListItem {
  id: string;
  title: string;
  subtitle: string | null;
  cover: string | null;
  updated_at: string;
  slide_count: number;
  preview_kicker?: string | null;
  preview_markdown?: string | null;
}

export interface SlideMutationResult {
  slides: Slide[];
}

export type LlmCapability = "inline_write" | "interpret" | "widget_generate";

export interface LlmModelConfig {
  id: string;
  supports_image_input: boolean;
  max_context_window?: number | null;
  max_output_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  frequency_penalty?: number | null;
  presence_penalty?: number | null;
}

export interface Workspace {
  id: string;
  name: string;
  llm_base_url: string;
  llm_model: string | null;
  llm_caps: Record<string, boolean>;
  llm_models: LlmModelConfig[];
  llm_capability_models: Record<LlmCapability, string | null>;
  llm_key_configured: boolean;
}

export interface WorkspacePatch {
  llm_base_url?: string;
  llm_api_key?: string;
  llm_model?: string;
  llm_caps?: Record<string, boolean>;
  llm_models?: LlmModelConfig[];
  llm_capability_models?: Partial<Record<LlmCapability, string | null>>;
}

export type LlmPurpose = "inline_write" | "interpret" | "widget_generate" | "summarise";

export interface SessionListItem {
  id: string;
  deck_id: string;
  code: string;
  started_at: string;
  ended_at: string | null;
}

export interface SessionPublic {
  id: string;
  code: string;
  deck_title: string;
  started_at: string;
  ended_at: string | null;
}

export interface SessionSlide {
  id: string;
  session_id: string;
  parent_slide_id: string | null;
  widget_id: string | null;
  position: number;
  kind: string;
  spec: Record<string, unknown>;
  results: Record<string, unknown>;
  inverted_theme: boolean;
  opened_at: string;
  closed_at: string | null;
}

// ---- Live interaction (poll / open-question) typed shapes ----

export interface PollChoice {
  id: string;
  label: string;
}

export interface PollSpec {
  type: "poll";
  question: string;
  choices: PollChoice[];
  config: {
    allow_other: boolean;
    show_results_live: boolean;
    anonymous: boolean;
  };
  state: { voting_closed: boolean; choices_locked: boolean };
}

export interface PollResults {
  tally: Record<string, number>;
  voters: number;
  other_responses?: { id: string; text: string; ref: string }[];
}

export interface QuestionSpec {
  type: "question";
  prompt: string;
  config: { anonymous: boolean };
}

export interface PromotedAnswer {
  id: string;
  text: string;
  display_name: string | null;
  anon: boolean;
}

export interface QuestionResults {
  promoted: PromotedAnswer[];
  total_answers: number;
}

export interface RandomAudienceSpec {
  type: "random";
  count: number;
}

export interface RandomAudiencePick {
  participant_ref: string;
  display_name: string | null;
  anon: boolean;
}

export interface RandomAudienceResults {
  requested_count: number;
  eligible_count: number;
  picked: RandomAudiencePick[];
}

export interface OpenAnswer {
  id: number;
  text: string;
  participant_ref: string;
  display_name: string | null;
  anon: boolean;
  occurred_at: string;
  promoted: boolean;
}

export interface SessionQuestion {
  id: string;
  slide_id: string | null;
  participant_ref: string;
  anon: boolean;
  text: string;
  raised_at: string;
  answered_at: string | null;
}

export interface SessionSnapshot {
  id: string;
  code: string;
  deck_id: string;
  deck_title: string;
  owner_id: string;
  started_at: string;
  ended_at: string | null;
  current_slide_id: string | null;
  sections: Section[];
  slides: Slide[];
  session_slides: SessionSlide[];
  questions: SessionQuestion[];
  audience_count: number;
  /** Widgets v2 Step 4 — current state for every Loud iframe widget placed
   * on this session's deck. Empty until any audience contributes. */
  placement_states?: PlacementState[];
}

export interface GuestJoinResponse {
  session_id: string;
  participant_id: string;
  participant_ref: string;
  token: string;
  display_name: string | null;
  anon: boolean;
}

export interface PreviewFakeGuest {
  participant_id: string;
  participant_ref: string;
  display_name: string;
  token: string;
}

export interface PreviewSessionResponse {
  session_id: string;
  code: string;
  fake_guests: PreviewFakeGuest[];
}
