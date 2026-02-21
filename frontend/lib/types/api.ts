export type Pace = "relaxed" | "moderate" | "intensive";
export type TransportMode = "walking" | "public_transit" | "taxi" | "driving";
export type TravelersType = "solo" | "couple" | "family" | "friends" | "elderly";
export type TimeSlot = "morning" | "lunch" | "afternoon" | "dinner" | "evening";

export type POI = {
  id: string;
  name: string;
  city: string;
  lat: number;
  lon: number;
  themes: string[];
  duration_hours: number;
  cost: number;
  indoor: boolean;
  open_time?: string | null;
  open_hours?: string | null;
  description: string;
  ticket_price?: number;
  reservation_required?: boolean;
  requires_reservation?: boolean;
  closed_rules?: string;
  fact_sources?: Record<string, string>;
};

export type ScheduleItem = {
  poi: POI;
  time_slot: TimeSlot;
  start_time?: string | null;
  end_time?: string | null;
  travel_minutes: number;
  notes: string;
  is_backup: boolean;
};

export type ItineraryDay = {
  day_number: number;
  date?: string | null;
  schedule: ScheduleItem[];
  backups: ScheduleItem[];
  day_summary: string;
  estimated_cost: number;
  total_travel_minutes: number;
};

export type Itinerary = {
  city: string;
  days: ItineraryDay[];
  total_cost: number;
  assumptions: string[];
  summary: string;
  budget_breakdown?: {
    tickets?: number;
    local_transport?: number;
    food_min?: number;
  };
  budget_source_breakdown?: {
    tickets?: string;
    local_transport?: string;
    food_min?: string;
  };
  budget_confidence_breakdown?: {
    tickets?: number;
    local_transport?: number;
    food_min?: number;
  };
  budget_confidence_score?: number;
  budget_as_of?: string;
  minimum_feasible_budget?: number;
  budget_warning?: string;
  unknown_fields?: string[];
  confidence_score?: number;
  degrade_level?: string;
  violations?: string[];
  repair_actions?: string[];
  trace_id?: string;
};

export type PlanRequest = {
  message: string;
  constraints?: Record<string, unknown>;
  user_profile?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type ChatRequest = {
  session_id: string;
  message: string;
  constraints?: Record<string, unknown>;
  user_profile?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type PlanResponse = {
  status: "done" | "clarifying" | "error" | string;
  message: string;
  itinerary?: Itinerary | null;
  session_id: string;
  request_id?: string;
  trace_id?: string;
  degrade_level?: string;
  confidence_score?: number | null;
  issues?: string[];
  next_questions?: string[];
  field_evidence?: Record<string, unknown>;
};

export type SessionHistoryItemResponse = {
  request_id: string;
  trace_id: string;
  message: string;
  status: string;
  degrade_level: string;
  confidence_score?: number | null;
  run_fingerprint?: Record<string, unknown>;
  created_at: string;
};

export type SessionHistoryResponse = {
  session_id: string;
  items: SessionHistoryItemResponse[];
};

export type SessionSummaryResponse = {
  session_id: string;
  updated_at: string;
  last_status: string;
  last_trace_id: string;
};

export type SessionListResponse = {
  items: SessionSummaryResponse[];
};

export type ArtifactPayloadResponse = {
  artifact_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type PlanExportResponse = {
  request_id: string;
  session_id: string;
  trace_id: string;
  message: string;
  constraints?: Record<string, unknown>;
  user_profile?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  status: string;
  degrade_level: string;
  confidence_score?: number | null;
  run_fingerprint?: Record<string, unknown>;
  itinerary?: Itinerary | null;
  issues?: string[];
  next_questions?: string[];
  field_evidence?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  created_at: string;
  artifacts?: ArtifactPayloadResponse[];
};

export type HealthResponse = {
  status: string;
};

export type DiagnosticsResponse = {
  tools?: {
    poi?: string;
    route?: string;
    budget?: string;
    weather?: string;
    calendar?: string;
    llm?: string;
  };
  signing_enabled?: boolean;
  cache?: {
    poi?: Record<string, unknown>;
    route?: Record<string, unknown>;
    weather?: Record<string, unknown>;
  };
  sessions?: {
    backend?: string;
    active?: number;
  };
  runtime_flags?: {
    engine_version?: string;
    strict_required_fields?: boolean;
  };
  plan_metrics?: {
    total_requests?: number;
    status_counts?: Record<string, number>;
    engine_counts?: Record<string, number>;
    strict_required_fields?: Record<string, number>;
    latency?: {
      count?: number;
      avg_ms?: number;
      max_ms?: number;
      p95_ms?: number;
    };
    p95_latency_ms?: number;
    success_rate?: number;
    llm_calls_per_request?: number;
    degrade_counts?: Record<string, number>;
    last_requests?: Array<Record<string, unknown>>;
  };
};

export type PlanFormValues = {
  city: string;
  days: number;
  budget?: number;
  pace: Pace;
  theme: string;
  transport: TransportMode;
  travelers: TravelersType;
  date_start?: string;
  date_end?: string;
  extraNotes?: string;
};

export type StoredPlanHistory = {
  id: string;
  createdAt: string;
  request: PlanFormValues;
  response: PlanResponse;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  itinerary?: Itinerary | null;
};

export type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
};
