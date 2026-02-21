import { NextRequest, NextResponse } from "next/server";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade"
]);

function getBackendBaseUrl(): string {
  const value = process.env.API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function buildTargetUrl(request: NextRequest, path: string[]): string {
  const normalized = path.map((segment) => encodeURIComponent(segment)).join("/");
  return `${getBackendBaseUrl()}/${normalized}${request.nextUrl.search}`;
}

function buildRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }

  const requestId = request.headers.get("x-request-id");
  if (requestId) {
    headers.set("X-Request-ID", requestId);
  }

  const incomingAuth = request.headers.get("authorization");
  if (incomingAuth) {
    headers.set("Authorization", incomingAuth);
  } else {
    const backendToken = process.env.API_BEARER_TOKEN?.trim();
    if (backendToken) {
      headers.set("Authorization", `Bearer ${backendToken}`);
    }
  }

  return headers;
}

function buildResponseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  const cacheControl = upstream.headers.get("cache-control");
  if (cacheControl) {
    headers.set("Cache-Control", cacheControl);
  }
  const requestId = upstream.headers.get("x-request-id");
  if (requestId) {
    headers.set("X-Request-ID", requestId);
  }
  return headers;
}

async function proxyRequest(
  request: NextRequest,
  context: { params: { path: string[] } },
): Promise<NextResponse> {
  const { path } = context.params;
  if (!Array.isArray(path) || path.length === 0) {
    return NextResponse.json({ detail: "Invalid proxy path" }, { status: 400 });
  }

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const targetUrl = buildTargetUrl(request, path);
  const requestHeaders = buildRequestHeaders(request);

  try {
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers: requestHeaders,
      body,
      cache: "no-store",
      redirect: "manual",
    });

    const raw = await upstream.arrayBuffer();
    const responseHeaders = buildResponseHeaders(upstream);

    for (const [name, value] of upstream.headers.entries()) {
      if (HOP_BY_HOP_HEADERS.has(name.toLowerCase())) {
        continue;
      }
      if (name.toLowerCase() === "content-type" || name.toLowerCase() === "cache-control") {
        continue;
      }
      if (name.toLowerCase() === "x-request-id") {
        continue;
      }
      responseHeaders.set(name, value);
    }

    return new NextResponse(raw, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { detail: "Backend upstream is unavailable" },
      { status: 502 },
    );
  }
}

export async function GET(
  request: NextRequest,
  context: { params: { path: string[] } },
): Promise<NextResponse> {
  return proxyRequest(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: { path: string[] } },
): Promise<NextResponse> {
  return proxyRequest(request, context);
}
