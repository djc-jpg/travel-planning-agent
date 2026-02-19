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
  description: string;
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
};

export type PlanRequest = {
  message: string;
};

export type ChatRequest = {
  session_id: string;
  message: string;
};

export type PlanResponse = {
  status: "done" | "clarifying" | "error" | string;
  message: string;
  itinerary?: Itinerary | null;
  session_id: string;
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
