export class ApiError extends Error {
  readonly status: number;
  readonly details?: unknown;
  readonly isTimeout: boolean;
  readonly isNetworkError: boolean;

  constructor(
    message: string,
    options: {
      status?: number;
      details?: unknown;
      isTimeout?: boolean;
      isNetworkError?: boolean;
    } = {}
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status ?? 0;
    this.details = options.details;
    this.isTimeout = options.isTimeout ?? false;
    this.isNetworkError = options.isNetworkError ?? false;
  }
}

export function toUserMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Request failed. Please try again.";
  }

  if (error.isTimeout) {
    return "Request timed out. Please try again later.";
  }
  if (error.status === 401) {
    return "Unauthorized (401). Please configure a valid bearer token.";
  }
  if (error.status === 403) {
    return "Forbidden (403). The bearer token is invalid.";
  }
  if (error.status === 429) {
    return "Too many requests (429). Please retry later.";
  }
  if (error.status === 422) {
    return "Validation failed (422). Please check your input.";
  }
  if (error.status >= 500) {
    return "Service temporarily unavailable (5xx). Please retry later.";
  }
  if (error.isNetworkError) {
    return "Network error. Cannot reach the backend service.";
  }
  return error.message || "Request failed. Please try again.";
}

