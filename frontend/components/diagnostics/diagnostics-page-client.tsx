"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, RefreshCw, Server } from "lucide-react";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { getDiagnosticsToken, saveDiagnosticsToken } from "@/lib/storage";

async function measure<T>(fn: () => Promise<T>): Promise<{ data: T; latencyMs: number }> {
  const start = performance.now();
  const data = await fn();
  const end = performance.now();
  return { data, latencyMs: Math.round(end - start) };
}

export function DiagnosticsPageClient() {
  const [token, setToken] = useState("");

  useEffect(() => {
    setToken(getDiagnosticsToken());
  }, []);

  const healthQuery = useQuery({
    queryKey: ["health", token],
    queryFn: () => measure(() => apiClient.health(token || undefined))
  });

  const diagnosticsQuery = useQuery({
    queryKey: ["diagnostics", token],
    queryFn: () => measure(() => apiClient.diagnostics(token || undefined))
  });

  return (
    <main className="page-container space-y-6">
      <div>
        <h1 className="page-title">系统状态</h1>
        <p className="page-subtitle">检查 /health 与 /diagnostics 可用性、延迟和后端工具状态。</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>可选鉴权 Token</CardTitle>
          <CardDescription>如果后端启用鉴权，可在此输入 Bearer Token。</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="min-w-[260px] flex-1 space-y-1.5">
            <Label htmlFor="diag-token">Token</Label>
            <Input
              id="diag-token"
              placeholder="可选：Bearer Token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
            />
          </div>
          <Button
            variant="secondary"
            onClick={() => {
              saveDiagnosticsToken(token.trim());
              healthQuery.refetch();
              diagnosticsQuery.refetch();
            }}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            保存并刷新
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="h-4 w-4 text-primary" />
              Health
            </CardTitle>
            <CardDescription>GET /health</CardDescription>
          </CardHeader>
          <CardContent>
            {healthQuery.isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : healthQuery.isError ? (
              <Alert variant="destructive">{toUserMessage(healthQuery.error)}</Alert>
            ) : (
              <div className="space-y-1 text-sm">
                <p>
                  状态: <strong>{healthQuery.data?.data.status}</strong>
                </p>
                <p>延迟: {healthQuery.data?.latencyMs} ms</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="h-4 w-4 text-primary" />
              Diagnostics
            </CardTitle>
            <CardDescription>GET /diagnostics</CardDescription>
          </CardHeader>
          <CardContent>
            {diagnosticsQuery.isLoading ? (
              <Skeleton className="h-28 w-full" />
            ) : diagnosticsQuery.isError ? (
              <Alert variant="destructive">{toUserMessage(diagnosticsQuery.error)}</Alert>
            ) : (
              <div className="space-y-2 text-sm">
                <p>延迟: {diagnosticsQuery.data?.latencyMs} ms</p>
                <p>会话后端: {diagnosticsQuery.data?.data.sessions?.backend ?? "-"}</p>
                <p>活跃会话: {diagnosticsQuery.data?.data.sessions?.active ?? 0}</p>
                <p>LLM: {diagnosticsQuery.data?.data.tools?.llm ?? "-"}</p>
                <p>POI 工具: {diagnosticsQuery.data?.data.tools?.poi ?? "-"}</p>
                <p>签名启用: {diagnosticsQuery.data?.data.signing_enabled ? "是" : "否"}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
