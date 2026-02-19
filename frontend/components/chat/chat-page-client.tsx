"use client";

import { useMutation } from "@tanstack/react-query";
import { MessageSquarePlus, Send, Sparkles, Trash2 } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { toast } from "sonner";

import { ItineraryRenderer } from "@/components/itinerary-renderer";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { useChatSessions } from "@/hooks/use-chat-sessions";
import { apiClient } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { chatQuickPrompts } from "@/lib/constants";
import { inferDraftFromItinerary, inferDraftFromText } from "@/lib/plan-message";
import { getPlanDraft, savePlanDraft } from "@/lib/storage";
import type { ChatMessage, PlanFormValues, PlanResponse } from "@/lib/types/api";
import { randomId } from "@/lib/utils";

export function ChatPageClient() {
  const [input, setInput] = useState("");
  const [lastError, setLastError] = useState("");
  const { sessions, activeId, setActiveId, activeSession, createNewSession, appendMessage, deleteSession } =
    useChatSessions();

  const chatMutation = useMutation({
    mutationFn: async (payload: { sessionId: string; message: string }) =>
      apiClient.chat({
        session_id: payload.sessionId,
        message: payload.message
      }),
    onSuccess: (response: PlanResponse, payload) => {
      const assistantMessage: ChatMessage = {
        id: randomId("msg"),
        role: "assistant",
        content: response.message || "(空回复)",
        createdAt: new Date().toISOString(),
        itinerary: response.itinerary ?? null
      };
      appendMessage(payload.sessionId, assistantMessage);
      setLastError("");
    },
    onError: (error) => {
      const message = toUserMessage(error);
      setLastError(message);
      toast.error(message);
    }
  });

  const latestItinerary =
    activeSession?.messages
      .slice()
      .reverse()
      .find((message) => message.itinerary)?.itinerary ?? null;

  const sessionInfo = useMemo(() => {
    if (!activeSession) {
      return "未选择会话";
    }
    return `${activeSession.id} · ${activeSession.messages.length} 条消息`;
  }, [activeSession]);

  const handleSend = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeSession || !input.trim() || chatMutation.isPending) {
      return;
    }
    sendMessage(input.trim());
    setInput("");
  };

  const sendMessage = (messageText: string) => {
    if (!activeSession) {
      return;
    }
    const userMessage: ChatMessage = {
      id: randomId("msg"),
      role: "user",
      content: messageText,
      createdAt: new Date().toISOString()
    };
    appendMessage(activeSession.id, userMessage);
    chatMutation.mutate({ sessionId: activeSession.id, message: userMessage.content });
  };

  const handleApplyToPlan = () => {
    const current = getPlanDraft();
    const lastUserMessage =
      activeSession?.messages
        .slice()
        .reverse()
        .find((msg) => msg.role === "user")?.content ?? "";
    const patch = latestItinerary ? inferDraftFromItinerary(latestItinerary) : inferDraftFromText(lastUserMessage);
    if (!patch.city && !patch.days && !patch.budget) {
      toast.warning("未识别到可应用的城市/天数/预算信息");
      return;
    }
    const next: Partial<PlanFormValues> = { ...(current ?? {}), ...patch };
    savePlanDraft({
      city: next.city ?? "",
      days: next.days ?? 3,
      budget: next.budget,
      pace: next.pace ?? "moderate",
      theme: next.theme ?? "",
      transport: next.transport ?? "public_transit",
      travelers: next.travelers ?? "couple",
      date_start: next.date_start ?? "",
      date_end: next.date_end ?? "",
      extraNotes: next.extraNotes ?? ""
    });
    toast.success("已应用到 Plan 草稿，返回 Plan 页可直接生成");
  };

  return (
    <main className="page-container space-y-6">
      <div>
        <h1 className="page-title">智能对话调优</h1>
        <p className="page-subtitle">像和旅行顾问聊天一样，逐步微调你的行程安排。</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[260px_1fr_360px]">
        <Card className="h-[72vh] overflow-hidden">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">会话列表</CardTitle>
            <Button size="sm" onClick={createNewSession}>
              <MessageSquarePlus className="mr-2 h-4 w-4" />
              新建会话
            </Button>
          </CardHeader>
          <CardContent className="space-y-2 overflow-y-auto pb-4">
            {sessions.map((session) => (
              <div
                key={session.id}
                className={`rounded-md border p-2 ${session.id === activeId ? "border-primary bg-primary/5" : ""}`}
              >
                <button
                  className="w-full text-left"
                  onClick={() => setActiveId(session.id)}
                  aria-label={`切换到会话 ${session.title}`}
                >
                  <p className="truncate text-sm font-medium">{session.title}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {new Date(session.updatedAt).toLocaleString("zh-CN", { hour12: false })}
                  </p>
                </button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-1 h-7 px-2 text-xs text-muted-foreground"
                  onClick={() => deleteSession(session.id)}
                >
                  <Trash2 className="mr-1 h-3 w-3" />
                  删除
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="flex h-[72vh] flex-col overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base">对话窗口</CardTitle>
            <CardDescription>{sessionInfo}</CardDescription>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              {chatQuickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="rounded-full border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                  onClick={() => sendMessage(prompt)}
                >
                  <Sparkles className="mr-1 inline h-3 w-3" />
                  {prompt}
                </button>
              ))}
            </div>

            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-md border p-3">
              {activeSession?.messages.length ? (
                activeSession.messages.map((message) => (
                  <div
                    key={message.id}
                    className={`max-w-[92%] rounded-md p-3 text-sm ${
                      message.role === "user"
                        ? "ml-auto bg-primary text-primary-foreground"
                        : "bg-muted text-foreground"
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{message.content}</p>
                    <p className="mt-1 text-[11px] opacity-70">
                      {new Date(message.createdAt).toLocaleTimeString("zh-CN", { hour12: false })}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">发送第一条消息，开始优化你的行程。</p>
              )}
            </div>

            {lastError ? <Alert variant="destructive">{lastError}</Alert> : null}

            <form className="flex gap-2" onSubmit={handleSend}>
              <Input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="例如：第二天改成亲子路线，晚上安排夜景和美食"
              />
              <Button type="submit" disabled={chatMutation.isPending}>
                <Send className="mr-2 h-4 w-4" />
                发送
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="h-[72vh] overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base">行程预览侧栏</CardTitle>
            <CardDescription>若回复包含 itinerary，会自动同步显示。</CardDescription>
          </CardHeader>
          <CardContent className="flex h-[calc(72vh-110px)] flex-col gap-3 overflow-y-auto">
            <Button variant="secondary" onClick={handleApplyToPlan}>
              一键应用到 Plan 表单
            </Button>
            <Separator />
            {latestItinerary ? (
              <ItineraryRenderer itinerary={latestItinerary} compact />
            ) : (
              <p className="text-sm text-muted-foreground">当前会话暂无可预览行程。</p>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
