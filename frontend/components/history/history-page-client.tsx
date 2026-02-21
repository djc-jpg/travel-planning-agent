"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ItineraryRenderer } from "@/components/itinerary-renderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { usePlanHistory } from "@/hooks/use-plan-history";
import { apiClient } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { formatAssistantMessage } from "@/lib/itinerary-text";
import { inferDraftFromItinerary } from "@/lib/plan-message";
import { savePlanDraft } from "@/lib/storage";
import type {
  PlanExportResponse,
  PlanFormValues,
  SessionHistoryItemResponse,
  SessionSummaryResponse,
  StoredPlanHistory
} from "@/lib/types/api";

type RunFingerprint = {
  run_mode?: string;
  poi_provider?: string;
  route_provider?: string;
  llm_provider?: string;
  strict_external_data?: boolean;
  env_source?: string;
  trace_id?: string;
};

const defaultDraft: PlanFormValues = {
  city: "",
  days: 3,
  budget: undefined,
  pace: "moderate",
  theme: "",
  transport: "public_transit",
  travelers: "couple",
  date_start: "",
  date_end: "",
  extraNotes: ""
};

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function downloadText(filename: string, payload: string, contentType = "text/plain"): void {
  const blob = new Blob([payload], { type: contentType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function parseRunFingerprint(raw: Record<string, unknown> | undefined): RunFingerprint {
  if (!raw) {
    return {};
  }
  return {
    run_mode: typeof raw.run_mode === "string" ? raw.run_mode : undefined,
    poi_provider: typeof raw.poi_provider === "string" ? raw.poi_provider : undefined,
    route_provider: typeof raw.route_provider === "string" ? raw.route_provider : undefined,
    llm_provider: typeof raw.llm_provider === "string" ? raw.llm_provider : undefined,
    strict_external_data:
      typeof raw.strict_external_data === "boolean" ? raw.strict_external_data : undefined,
    env_source: typeof raw.env_source === "string" ? raw.env_source : undefined,
    trace_id: typeof raw.trace_id === "string" ? raw.trace_id : undefined
  };
}

function pickMetric(metrics: Record<string, unknown> | undefined, key: string): number | null {
  const value = metrics?.[key];
  return typeof value === "number" ? value : null;
}

export function HistoryPageClient() {
  const router = useRouter();
  const { history, removeHistory, clearHistory } = usePlanHistory();
  const [sessionId, setSessionId] = useState("");
  const [remoteItems, setRemoteItems] = useState<SessionHistoryItemResponse[]>([]);
  const [selectedExport, setSelectedExport] = useState<PlanExportResponse | null>(null);
  const [hasQueriedRemote, setHasQueriedRemote] = useState(false);
  const [markdownPending, setMarkdownPending] = useState(false);

  const recentSessionsQuery = useQuery({
    queryKey: ["recent-sessions"],
    queryFn: async () => apiClient.sessions(10),
    staleTime: 30_000
  });
  const recentSessions = recentSessionsQuery.data?.items ?? [];

  const queryHistoryMutation = useMutation({
    mutationFn: async (targetSessionId: string) => apiClient.sessionHistory(targetSessionId, 20),
    onSuccess: (response) => {
      setRemoteItems(response.items ?? []);
      setHasQueriedRemote(true);
      toast.success(`Loaded server history for ${response.session_id}`);
    },
    onError: (error) => {
      setRemoteItems([]);
      setHasQueriedRemote(true);
      toast.error(toUserMessage(error));
    }
  });

  const exportMutation = useMutation({
    mutationFn: async (requestId: string) => apiClient.planExport(requestId),
    onSuccess: (response) => {
      setSelectedExport(response);
      toast.success(`Loaded export ${response.request_id}`);
    },
    onError: (error) => {
      toast.error(toUserMessage(error));
    }
  });

  const activeRequestId = selectedExport?.request_id ?? "";

  const handleCopyMarkdown = async () => {
    if (!selectedExport) {
      return;
    }
    try {
      setMarkdownPending(true);
      const markdown = await apiClient.planExportMarkdown(selectedExport.request_id);
      await navigator.clipboard.writeText(markdown);
      toast.success("Markdown copied");
    } catch (error) {
      toast.error(toUserMessage(error));
    } finally {
      setMarkdownPending(false);
    }
  };

  const handleDownloadMarkdown = async () => {
    if (!selectedExport) {
      return;
    }
    try {
      setMarkdownPending(true);
      const markdown = await apiClient.planExportMarkdown(selectedExport.request_id);
      downloadText(`trip-export-${selectedExport.request_id}.md`, markdown, "text/markdown");
      toast.success("Markdown downloaded");
    } catch (error) {
      toast.error(toUserMessage(error));
    } finally {
      setMarkdownPending(false);
    }
  };

  const restoreToPlan = (itinerary: PlanExportResponse["itinerary"] | null | undefined) => {
    if (!itinerary) {
      toast.error("Export does not include itinerary");
      return;
    }
    const inferred = inferDraftFromItinerary(itinerary);
    savePlanDraft({ ...defaultDraft, ...inferred });
    toast.success("Draft restored to Plan page");
    router.push("/");
  };

  const handleRestoreLocal = (item: StoredPlanHistory) => {
    savePlanDraft(item.request);
    toast.success("Local draft restored to Plan page");
    router.push("/");
  };

  const handleQueryRemote = () => {
    const target = sessionId.trim();
    if (!target) {
      toast.error("Please input session_id");
      return;
    }
    queryHistoryMutation.mutate(target);
  };

  const handlePickSession = (session: SessionSummaryResponse) => {
    setSessionId(session.session_id);
    queryHistoryMutation.mutate(session.session_id);
  };

  const remoteSummary = useMemo(() => {
    if (!hasQueriedRemote) {
      return "Input a session_id or click a recent session to query server history.";
    }
    if (queryHistoryMutation.isPending) {
      return "Loading server history...";
    }
    if (remoteItems.length === 0) {
      return "No records found for this session.";
    }
    return `Found ${remoteItems.length} records.`;
  }, [hasQueriedRemote, queryHistoryMutation.isPending, remoteItems.length]);

  const selectedFingerprint = parseRunFingerprint(selectedExport?.run_fingerprint);
  const selectedMetrics = (selectedExport?.metrics ?? {}) as Record<string, unknown>;

  return (
    <main className="page-container space-y-6">
      <div>
        <h1 className="page-title">History and Export</h1>
        <p className="page-subtitle">
          Query server-side history by session, load exports, and restore itinerary back to the plan form.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Server History</CardTitle>
          <CardDescription>{remoteSummary}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {recentSessions.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {recentSessions.map((session) => (
                <Button
                  key={session.session_id}
                  variant={sessionId === session.session_id ? "default" : "outline"}
                  onClick={() => handlePickSession(session)}
                  disabled={queryHistoryMutation.isPending}
                >
                  {session.session_id} | {session.last_status || "unknown"} | {formatTime(session.updated_at)}
                </Button>
              ))}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={sessionId}
              onChange={(event) => setSessionId(event.target.value)}
              placeholder="Input session_id"
              className="max-w-md"
            />
            <Button onClick={handleQueryRemote} disabled={queryHistoryMutation.isPending}>
              Query
            </Button>
          </div>

          {remoteItems.length > 0 ? (
            <div className="space-y-3">
              {remoteItems.map((item) => {
                const runFingerprint = parseRunFingerprint(item.run_fingerprint);
                return (
                  <Card key={item.request_id}>
                    <CardHeader>
                      <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                        <span>{item.request_id}</span>
                        <Badge>{item.status}</Badge>
                        <Badge className="bg-secondary text-secondary-foreground">{item.degrade_level}</Badge>
                        {runFingerprint.run_mode ? (
                          <Badge className="bg-secondary text-secondary-foreground">
                            mode {runFingerprint.run_mode}
                          </Badge>
                        ) : null}
                      </CardTitle>
                      <CardDescription>
                        {formatTime(item.created_at)} | trace {item.trace_id}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      <p className="text-sm text-muted-foreground">
                        {formatAssistantMessage(item.message, false) || "Result is available; load export for details."}
                      </p>
                      <Button
                        variant={activeRequestId === item.request_id ? "default" : "secondary"}
                        onClick={() => exportMutation.mutate(item.request_id)}
                        disabled={exportMutation.isPending}
                      >
                        Load Export
                      </Button>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {selectedExport ? (
        <Card>
          <CardHeader>
            <CardTitle>Export Details</CardTitle>
            <CardDescription>
              request_id: {selectedExport.request_id} | session_id: {selectedExport.session_id}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={async () => {
                  await navigator.clipboard.writeText(JSON.stringify(selectedExport, null, 2));
                  toast.success("JSON copied");
                }}
              >
                Copy JSON
              </Button>
              <Button variant="secondary" onClick={handleCopyMarkdown} disabled={markdownPending}>
                Copy Markdown
              </Button>
              <Button
                variant="outline"
                onClick={() => downloadJson(`trip-export-${selectedExport.request_id}.json`, selectedExport)}
              >
                Download JSON
              </Button>
              <Button variant="outline" onClick={handleDownloadMarkdown} disabled={markdownPending}>
                Download Markdown
              </Button>
              <Button onClick={() => restoreToPlan(selectedExport.itinerary ?? null)}>Restore to Plan</Button>
            </div>

            <details className="rounded-md border p-3">
              <summary className="cursor-pointer text-sm font-medium">Run fingerprint and quality metrics</summary>
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Badge>run_mode: {selectedFingerprint.run_mode ?? "unknown"}</Badge>
                  <Badge>poi: {selectedFingerprint.poi_provider ?? "unknown"}</Badge>
                  <Badge>route: {selectedFingerprint.route_provider ?? "unknown"}</Badge>
                  <Badge>llm: {selectedFingerprint.llm_provider ?? "unknown"}</Badge>
                  <Badge>
                    strict: {typeof selectedFingerprint.strict_external_data === "boolean" ? String(selectedFingerprint.strict_external_data) : "unknown"}
                  </Badge>
                  <Badge>env: {selectedFingerprint.env_source ?? "unknown"}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  trace: {selectedFingerprint.trace_id ?? selectedExport.trace_id ?? "unknown"}
                </p>
                <div className="grid gap-1 text-sm text-muted-foreground">
                  <p>verified_fact_ratio: {pickMetric(selectedMetrics, "verified_fact_ratio")?.toFixed(4) ?? "n/a"}</p>
                  <p>unknown_fact_rate: {pickMetric(selectedMetrics, "unknown_fact_rate")?.toFixed(4) ?? "n/a"}</p>
                  <p>fallback_rate: {pickMetric(selectedMetrics, "fallback_rate")?.toFixed(4) ?? "n/a"}</p>
                  <p>routing_fixture_rate: {pickMetric(selectedMetrics, "routing_fixture_rate")?.toFixed(4) ?? "n/a"}</p>
                  <p>l0_real_routing_ratio: {pickMetric(selectedMetrics, "l0_real_routing_ratio")?.toFixed(4) ?? "n/a"}</p>
                </div>
              </div>
            </details>

            <Separator />
            {selectedExport.itinerary ? (
              <ItineraryRenderer itinerary={selectedExport.itinerary} compact />
            ) : (
              <p className="text-sm text-muted-foreground">This export has no itinerary payload.</p>
            )}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Local History (Browser)</CardTitle>
          <CardDescription>Keeps latest 10 local records for quick draft restore.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button variant="outline" onClick={clearHistory} disabled={history.length === 0}>
            Clear local history
          </Button>

          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No local records yet.</p>
          ) : (
            history.map((item) => (
              <Card key={item.id}>
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <span>{item.request.city || "Unnamed city"}</span>
                    <Badge>{item.request.days} days</Badge>
                    <Badge className="bg-secondary text-secondary-foreground">
                      {item.request.budget ? `¥${item.request.budget}/day` : "Budget not set"}
                    </Badge>
                  </CardTitle>
                  <CardDescription>
                    {new Date(item.createdAt).toLocaleString("zh-CN", { hour12: false })} | status {item.response.status}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => handleRestoreLocal(item)}>Restore to Plan</Button>
                    <Button variant="secondary" onClick={() => removeHistory(item.id)}>
                      Delete
                    </Button>
                  </div>
                  <Separator />
                  {item.response.itinerary ? (
                    <ItineraryRenderer itinerary={item.response.itinerary} compact />
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {formatAssistantMessage(item.response.message, false) || "No itinerary returned"}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </CardContent>
      </Card>
    </main>
  );
}
