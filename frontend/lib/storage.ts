import type { ChatSession, PlanFormValues, StoredPlanHistory } from "@/lib/types/api";

const KEYS = {
  history: "trip_agent_plan_history_v1",
  planDraft: "trip_agent_plan_draft_v1",
  chatSessions: "trip_agent_chat_sessions_v1",
  diagnosticsToken: "trip_agent_diagnostics_token_v1"
} as const;

function safeParse<T>(value: string | null, fallback: T): T {
  if (!value) {
    return fallback;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function inBrowser(): boolean {
  return typeof window !== "undefined";
}

export function getPlanHistory(): StoredPlanHistory[] {
  if (!inBrowser()) {
    return [];
  }
  return safeParse<StoredPlanHistory[]>(window.localStorage.getItem(KEYS.history), []);
}

export function savePlanHistory(history: StoredPlanHistory[]): void {
  if (!inBrowser()) {
    return;
  }
  window.localStorage.setItem(KEYS.history, JSON.stringify(history.slice(0, 10)));
}

export function getPlanDraft(): PlanFormValues | null {
  if (!inBrowser()) {
    return null;
  }
  return safeParse<PlanFormValues | null>(window.localStorage.getItem(KEYS.planDraft), null);
}

export function savePlanDraft(values: PlanFormValues): void {
  if (!inBrowser()) {
    return;
  }
  window.localStorage.setItem(KEYS.planDraft, JSON.stringify(values));
}

export function getChatSessions(): ChatSession[] {
  if (!inBrowser()) {
    return [];
  }
  return safeParse<ChatSession[]>(window.localStorage.getItem(KEYS.chatSessions), []);
}

export function saveChatSessions(sessions: ChatSession[]): void {
  if (!inBrowser()) {
    return;
  }
  window.localStorage.setItem(KEYS.chatSessions, JSON.stringify(sessions));
}

export function getDiagnosticsToken(): string {
  if (!inBrowser()) {
    return "";
  }
  return window.localStorage.getItem(KEYS.diagnosticsToken) ?? "";
}

export function saveDiagnosticsToken(token: string): void {
  if (!inBrowser()) {
    return;
  }
  window.localStorage.setItem(KEYS.diagnosticsToken, token);
}
