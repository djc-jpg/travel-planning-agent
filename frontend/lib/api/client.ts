import type {
  ChatRequest,
  DiagnosticsResponse,
  HealthResponse,
  PlanExportResponse,
  PlanRequest,
  PlanResponse,
  SessionHistoryResponse,
  SessionListResponse
} from "@/lib/types/api";

import { ApiError } from "./errors";

type RetryPolicy = {
  retries: number;
  backoffMs: number;
};

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
  timeoutMs?: number;
  authToken?: string;
  retryPolicy?: RetryPolicy;
};

const DEFAULT_TIMEOUT_MS = 20_000;
const DEFAULT_RETRY_POLICY: RetryPolicy = {
  retries: 1,
  backoffMs: 500
};

function getBaseUrl(): string {
  return "/api/backend";
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function parseJsonSafe(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function shouldRetry(error: ApiError, method: string, attempt: number, retries: number): boolean {
  if (attempt >= retries) {
    return false;
  }
  if (method !== "GET") {
    return false;
  }
  if (error.isTimeout || error.isNetworkError) {
    return true;
  }
  return error.status === 429 || error.status >= 500;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const retryPolicy = options.retryPolicy ?? DEFAULT_RETRY_POLICY;
  const baseUrl = getBaseUrl();
  const authToken = options.authToken?.trim();

  for (let attempt = 0; ; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {})
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal
      });

      const payload = await parseJsonSafe(response);

      if (!response.ok) {
        const message =
          typeof payload === "object" && payload && "detail" in payload
            ? String((payload as { detail: unknown }).detail)
            : `Request failed with ${response.status}`;
        throw new ApiError(message, {
          status: response.status,
          details: payload
        });
      }

      return payload as T;
    } catch (error: unknown) {
      const apiError =
        error instanceof ApiError
          ? error
          : error instanceof DOMException && error.name === "AbortError"
            ? new ApiError("Request timeout", { isTimeout: true })
            : new ApiError("Network error", { isNetworkError: true });

      if (!shouldRetry(apiError, method, attempt, retryPolicy.retries)) {
        throw apiError;
      }
      const waitMs = retryPolicy.backoffMs * (attempt + 1);
      await sleep(waitMs);
    } finally {
      clearTimeout(timeout);
    }
  }
}

export const apiClient = {
  async plan(input: PlanRequest): Promise<PlanResponse> {
    return request<PlanResponse>("/plan", {
      method: "POST",
      body: input,
      timeoutMs: 60_000,
      retryPolicy: { retries: 0, backoffMs: 0 }
    });
  },
  async chat(input: ChatRequest): Promise<PlanResponse> {
    return request<PlanResponse>("/chat", {
      method: "POST",
      body: input,
      timeoutMs: 60_000,
      retryPolicy: { retries: 0, backoffMs: 0 }
    });
  },
  async health(authToken?: string): Promise<HealthResponse> {
    return request<HealthResponse>("/health", {
      method: "GET",
      authToken
    });
  },
  async diagnostics(authToken?: string): Promise<DiagnosticsResponse> {
    return request<DiagnosticsResponse>("/diagnostics", {
      method: "GET",
      authToken
    });
  },
  async sessionHistory(sessionId: string, limit = 20): Promise<SessionHistoryResponse> {
    const safeLimit = Math.max(1, Math.min(100, limit));
    const encoded = encodeURIComponent(sessionId);
    return request<SessionHistoryResponse>(`/sessions/${encoded}/history?limit=${safeLimit}`, {
      method: "GET"
    });
  },
  async sessions(limit = 20): Promise<SessionListResponse> {
    const safeLimit = Math.max(1, Math.min(100, limit));
    return request<SessionListResponse>(`/sessions?limit=${safeLimit}`, {
      method: "GET"
    });
  },
  async planExport(requestId: string): Promise<PlanExportResponse> {
    const encoded = encodeURIComponent(requestId);
    return request<PlanExportResponse>(`/plans/${encoded}/export`, {
      method: "GET"
    });
  },
  async planExportMarkdown(requestId: string): Promise<string> {
    const encoded = encodeURIComponent(requestId);
    return request<string>(`/plans/${encoded}/export?format=markdown`, {
      method: "GET"
    });
  }
};
