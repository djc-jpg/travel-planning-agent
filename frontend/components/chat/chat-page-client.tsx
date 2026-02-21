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
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useChatSessions } from "@/hooks/use-chat-sessions";
import { apiClient } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { chatQuickPrompts } from "@/lib/constants";
import { formatAssistantMessage } from "@/lib/itinerary-text";
import { inferDraftFromItinerary, inferDraftFromText } from "@/lib/plan-message";
import { getPlanDraft, savePlanDraft } from "@/lib/storage";
import type { ChatMessage, ChatRequest, PlanFormValues, PlanResponse } from "@/lib/types/api";
import { randomId } from "@/lib/utils";

type ChatMutationPayload = {
  sessionId: string;
  message: string;
  metadata?: ChatRequest["metadata"];
};

type EditPatchPayload = {
  edit_patch: {
    replace_stop?: {
      day_number: number;
      old_poi?: string;
      new_poi: string;
    };
    add_stop?: {
      day_number: number;
      poi: string;
    };
    remove_stop?: {
      day_number: number;
      poi: string;
    };
    adjust_time?: {
      day_number: number;
      poi?: string;
      window: string;
    };
    lunch_break?: {
      day_number?: number;
      window: string;
    };
    instruction?: string;
  };
};

function normalizeDay(value: string): number | undefined {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return undefined;
  }
  return parsed;
}

export function ChatPageClient() {
  const [input, setInput] = useState("");
  const [lastError, setLastError] = useState("");
  const [replaceDay, setReplaceDay] = useState("1");
  const [replaceOldPoi, setReplaceOldPoi] = useState("");
  const [replaceNewPoi, setReplaceNewPoi] = useState("");
  const [addDay, setAddDay] = useState("1");
  const [addPoi, setAddPoi] = useState("");
  const [removeDay, setRemoveDay] = useState("1");
  const [removePoi, setRemovePoi] = useState("");
  const [adjustDay, setAdjustDay] = useState("1");
  const [adjustPoi, setAdjustPoi] = useState("");
  const [adjustWindow, setAdjustWindow] = useState("14:00-16:00");
  const [lunchDay, setLunchDay] = useState("");
  const [lunchWindow, setLunchWindow] = useState("12:00-13:00");
  const { sessions, activeId, setActiveId, activeSession, createNewSession, appendMessage, deleteSession } =
    useChatSessions();

  const chatMutation = useMutation({
    mutationFn: async (payload: ChatMutationPayload) =>
      apiClient.chat({
        session_id: payload.sessionId,
        message: payload.message,
        metadata: payload.metadata
      }),
    onSuccess: (response: PlanResponse, payload) => {
      const assistantMessage: ChatMessage = {
        id: randomId("msg"),
        role: "assistant",
        content: formatAssistantMessage(response.message, Boolean(response.itinerary)),
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
    return `${activeSession.id} | ${activeSession.messages.length} 条消息`;
  }, [activeSession]);

  const sendMessage = (messageText: string, metadata?: ChatRequest["metadata"]) => {
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
    chatMutation.mutate({ sessionId: activeSession.id, message: userMessage.content, metadata });
  };

  const handleSend = (event: FormEvent) => {
    event.preventDefault();
    if (!activeSession || !input.trim() || chatMutation.isPending) {
      return;
    }
    sendMessage(input.trim());
    setInput("");
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
    toast.success("已应用到 Plan 草稿，返回 Plan 页面可直接生成");
  };

  const handleReplaceStopPatch = () => {
    if (!activeSession || chatMutation.isPending) {
      return;
    }
    const day = normalizeDay(replaceDay);
    const newPoi = replaceNewPoi.trim();
    const oldPoi = replaceOldPoi.trim();
    if (!day || !newPoi) {
      toast.error("替换点位至少需要：天数 + 新点位名称");
      return;
    }

    const patch: EditPatchPayload = {
      edit_patch: {
        replace_stop: {
          day_number: day,
          ...(oldPoi ? { old_poi: oldPoi } : {}),
          new_poi: newPoi
        },
        instruction: `replace_stop day=${day}`
      }
    };

    const text = oldPoi
      ? `请把第${day}天的「${oldPoi}」替换成「${newPoi}」`
      : `请在第${day}天加入「${newPoi}」，并调整当天安排`;
    sendMessage(text, patch);
    setReplaceNewPoi("");
  };

  const handleLunchBreakPatch = () => {
    if (!activeSession || chatMutation.isPending) {
      return;
    }
    const day = normalizeDay(lunchDay);
    const windowText = lunchWindow.trim() || "12:00-13:00";
    const patch: EditPatchPayload = {
      edit_patch: {
        lunch_break: {
          ...(day ? { day_number: day } : {}),
          window: windowText
        },
        instruction: day ? `lunch_break day=${day}` : "lunch_break all"
      }
    };

    const text = day
      ? `请在第${day}天加入午休时间（${windowText}）`
      : `请在每天加入午休时间（${windowText}）`;
    sendMessage(text, patch);
  };

  const handleAddStopPatch = () => {
    if (!activeSession || chatMutation.isPending) {
      return;
    }
    const day = normalizeDay(addDay);
    const poi = addPoi.trim();
    if (!day || !poi) {
      toast.error("添加点位至少需要：天数 + 点位名称");
      return;
    }

    const patch: EditPatchPayload = {
      edit_patch: {
        add_stop: { day_number: day, poi },
        instruction: `add_stop day=${day}`
      }
    };

    sendMessage(`请在第${day}天增加「${poi}」并同步调整行程`, patch);
    setAddPoi("");
  };

  const handleRemoveStopPatch = () => {
    if (!activeSession || chatMutation.isPending) {
      return;
    }
    const day = normalizeDay(removeDay);
    const poi = removePoi.trim();
    if (!day || !poi) {
      toast.error("删除点位至少需要：天数 + 点位名称");
      return;
    }

    const patch: EditPatchPayload = {
      edit_patch: {
        remove_stop: { day_number: day, poi },
        instruction: `remove_stop day=${day}`
      }
    };

    sendMessage(`请删除第${day}天的「${poi}」并重排当天行程`, patch);
    setRemovePoi("");
  };

  const handleAdjustTimePatch = () => {
    if (!activeSession || chatMutation.isPending) {
      return;
    }
    const day = normalizeDay(adjustDay);
    const windowText = adjustWindow.trim();
    const poi = adjustPoi.trim();
    if (!day || !windowText) {
      toast.error("调时至少需要：天数 + 时间窗");
      return;
    }

    const patch: EditPatchPayload = {
      edit_patch: {
        adjust_time: {
          day_number: day,
          ...(poi ? { poi } : {}),
          window: windowText
        },
        instruction: `adjust_time day=${day}`
      }
    };

    const text = poi
      ? `请把第${day}天「${poi}」调整到 ${windowText}`
      : `请把第${day}天行程时间调整到 ${windowText}`;
    sendMessage(text, patch);
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
                activeSession.messages.map((message) => {
                  const shownContent =
                    message.role === "assistant"
                      ? formatAssistantMessage(message.content, Boolean(message.itinerary))
                      : message.content;
                  return (
                    <div
                      key={message.id}
                      className={`max-w-[92%] rounded-md p-3 text-sm ${
                        message.role === "user"
                          ? "ml-auto bg-primary text-primary-foreground"
                          : "bg-muted text-foreground"
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{shownContent}</p>
                      <p className="mt-1 text-[11px] opacity-70">
                        {new Date(message.createdAt).toLocaleTimeString("zh-CN", { hour12: false })}
                      </p>
                    </div>
                  );
                })
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
            <CardTitle className="text-base">行程预览与局部编辑</CardTitle>
            <CardDescription>支持结构化 edit patch，尽量只改局部，不整条推倒重来。</CardDescription>
          </CardHeader>
          <CardContent className="flex h-[calc(72vh-110px)] flex-col gap-3 overflow-y-auto">
            <Button variant="secondary" onClick={handleApplyToPlan}>
              一键应用到 Plan 表单
            </Button>
            <Separator />

            <div className="space-y-2 rounded-md border p-3">
              <p className="text-sm font-medium">替换点位</p>
              <div className="grid gap-2">
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="replace-day">天数</Label>
                  <Input
                    id="replace-day"
                    value={replaceDay}
                    onChange={(event) => setReplaceDay(event.target.value)}
                    placeholder="例如 2"
                  />
                </div>
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="replace-old">旧点位</Label>
                  <Input
                    id="replace-old"
                    value={replaceOldPoi}
                    onChange={(event) => setReplaceOldPoi(event.target.value)}
                    placeholder="可选，例如 故宫"
                  />
                </div>
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="replace-new">新点位</Label>
                  <Input
                    id="replace-new"
                    value={replaceNewPoi}
                    onChange={(event) => setReplaceNewPoi(event.target.value)}
                    placeholder="必填，例如 颐和园"
                  />
                </div>
                <Button onClick={handleReplaceStopPatch} disabled={chatMutation.isPending || !activeSession}>
                  发送替换 patch
                </Button>
              </div>
            </div>

            <div className="space-y-2 rounded-md border p-3">
              <p className="text-sm font-medium">添加点位</p>
              <div className="grid gap-2">
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="add-day">天数</Label>
                  <Input
                    id="add-day"
                    value={addDay}
                    onChange={(event) => setAddDay(event.target.value)}
                    placeholder="例如 2"
                  />
                </div>
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="add-poi">点位</Label>
                  <Input
                    id="add-poi"
                    value={addPoi}
                    onChange={(event) => setAddPoi(event.target.value)}
                    placeholder="例如 景山公园"
                  />
                </div>
                <Button onClick={handleAddStopPatch} disabled={chatMutation.isPending || !activeSession}>
                  发送添加 patch
                </Button>
              </div>
            </div>

            <div className="space-y-2 rounded-md border p-3">
              <p className="text-sm font-medium">删除点位</p>
              <div className="grid gap-2">
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="remove-day">天数</Label>
                  <Input
                    id="remove-day"
                    value={removeDay}
                    onChange={(event) => setRemoveDay(event.target.value)}
                    placeholder="例如 2"
                  />
                </div>
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="remove-poi">点位</Label>
                  <Input
                    id="remove-poi"
                    value={removePoi}
                    onChange={(event) => setRemovePoi(event.target.value)}
                    placeholder="例如 故宫"
                  />
                </div>
                <Button onClick={handleRemoveStopPatch} disabled={chatMutation.isPending || !activeSession}>
                  发送删除 patch
                </Button>
              </div>
            </div>

            <div className="space-y-2 rounded-md border p-3">
              <p className="text-sm font-medium">调整时间</p>
              <div className="grid gap-2">
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="adjust-day">天数</Label>
                  <Input
                    id="adjust-day"
                    value={adjustDay}
                    onChange={(event) => setAdjustDay(event.target.value)}
                    placeholder="例如 1"
                  />
                </div>
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="adjust-poi">点位</Label>
                  <Input
                    id="adjust-poi"
                    value={adjustPoi}
                    onChange={(event) => setAdjustPoi(event.target.value)}
                    placeholder="可选，例如 天安门"
                  />
                </div>
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="adjust-window">时间窗</Label>
                  <Input
                    id="adjust-window"
                    value={adjustWindow}
                    onChange={(event) => setAdjustWindow(event.target.value)}
                    placeholder="例如 14:00-16:00 / 下午"
                  />
                </div>
                <Button onClick={handleAdjustTimePatch} disabled={chatMutation.isPending || !activeSession}>
                  发送调时 patch
                </Button>
              </div>
            </div>

            <div className="space-y-2 rounded-md border p-3">
              <p className="text-sm font-medium">添加午休</p>
              <div className="grid gap-2">
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="lunch-day">天数</Label>
                  <Input
                    id="lunch-day"
                    value={lunchDay}
                    onChange={(event) => setLunchDay(event.target.value)}
                    placeholder="可选，留空表示每天"
                  />
                </div>
                <div className="grid grid-cols-[80px_1fr] items-center gap-2">
                  <Label htmlFor="lunch-window">时间窗</Label>
                  <Input
                    id="lunch-window"
                    value={lunchWindow}
                    onChange={(event) => setLunchWindow(event.target.value)}
                    placeholder="例如 12:00-13:00"
                  />
                </div>
                <Button onClick={handleLunchBreakPatch} disabled={chatMutation.isPending || !activeSession}>
                  发送午休 patch
                </Button>
              </div>
            </div>

            <Separator />
            {latestItinerary ? (
              <ItineraryRenderer itinerary={latestItinerary} compact />
            ) : (
              <p className="text-sm text-muted-foreground">当前会话暂无可预览 itinerary。</p>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
