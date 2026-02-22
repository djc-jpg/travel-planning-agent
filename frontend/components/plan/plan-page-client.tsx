"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Check, Copy, Download, Loader2, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ItineraryRenderer } from "@/components/itinerary-renderer";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { usePlanHistory } from "@/hooks/use-plan-history";
import { apiClient } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import {
  budgetSuggestions,
  paceLabels,
  planPresets,
  themeSuggestions,
  transportLabels,
  travelerLabels
} from "@/lib/constants";
import { formatAssistantMessage } from "@/lib/itinerary-text";
import { buildPlanMessage, itineraryToMarkdown } from "@/lib/plan-message";
import { getPlanDraft, savePlanDraft } from "@/lib/storage";
import type {
  Itinerary,
  Pace,
  PlanFormValues,
  PlanRequest,
  PlanResponse,
  TransportMode,
  TravelersType
} from "@/lib/types/api";

type PlanRequestSnapshot = {
  city: string;
  days: number;
  budget_per_day?: number;
  date_start: string;
  date_end: string;
};

const planSchema = z.object({
  city: z.string().min(1, "请输入城市"),
  days: z.coerce.number().int().min(1, "至少 1 天").max(14, "最多 14 天"),
  budget: z.preprocess(
    (value) => {
      if (value === "" || value === null || value === undefined) {
        return undefined;
      }
      const num = Number(value);
      return Number.isNaN(num) ? undefined : num;
    },
    z.number().min(0).optional()
  ),
  pace: z.enum(["relaxed", "moderate", "intensive"]),
  theme: z.string().default(""),
  transport: z.enum(["walking", "public_transit", "taxi", "driving"]),
  travelers: z.enum(["solo", "couple", "family", "friends", "elderly"]),
  date_start: z.string().optional(),
  date_end: z.string().optional(),
  extraNotes: z.string().optional()
});

const defaultValues: PlanFormValues = {
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

const THEME_SPLITTER = /[、,，;；\s]+/;

function splitThemes(raw: string): string[] {
  const seen = new Set<string>();
  const rows: string[] = [];
  for (const value of raw.split(THEME_SPLITTER).map((item) => item.trim()).filter(Boolean)) {
    if (seen.has(value)) {
      continue;
    }
    seen.add(value);
    rows.push(value);
  }
  return rows;
}

function buildStructuredPlanPayload(values: PlanFormValues): PlanRequest {
  const city = values.city.trim();
  const themes = splitThemes(values.theme ?? "");

  const constraints: Record<string, unknown> = {
    city,
    days: values.days,
    pace: values.pace,
    transport_mode: values.transport
  };
  if (typeof values.budget === "number" && Number.isFinite(values.budget) && values.budget > 0) {
    constraints.budget_per_day = values.budget;
  }
  if (values.date_start) {
    constraints.date_start = values.date_start;
  }
  if (values.date_end) {
    constraints.date_end = values.date_end;
  }

  const user_profile: Record<string, unknown> = {
    travelers_type: values.travelers
  };
  if (themes.length > 0) {
    user_profile.themes = themes;
  }

  const metadata: Record<string, unknown> = {
    source: "web_plan_form",
    field_sources: {
      city: "user_form",
      days: "user_form",
      date_start: values.date_start ? "user_form" : "missing",
      date_end: values.date_end ? "user_form" : "missing"
    }
  };
  if (values.extraNotes?.trim()) {
    metadata.extra_notes = values.extraNotes.trim();
  }

  return {
    message: buildPlanMessage(values),
    constraints,
    user_profile,
    metadata
  };
}

function buildRequestSnapshot(values: PlanFormValues): PlanRequestSnapshot {
  const budget =
    typeof values.budget === "number" && Number.isFinite(values.budget) && values.budget > 0
      ? values.budget
      : undefined;
  return {
    city: values.city.trim(),
    days: values.days,
    budget_per_day: budget,
    date_start: (values.date_start ?? "").trim(),
    date_end: (values.date_end ?? "").trim()
  };
}

function normalizeDate(value: string | undefined | null): string {
  return String(value ?? "").trim().slice(0, 10);
}

export function PlanPageClient() {
  const [latestResponse, setLatestResponse] = useState<PlanResponse | null>(null);
  const [latestItinerary, setLatestItinerary] = useState<Itinerary | null>(null);
  const [requestSnapshot, setRequestSnapshot] = useState<PlanRequestSnapshot | null>(null);
  const { addHistory } = usePlanHistory();

  const form = useForm<PlanFormValues>({
    resolver: zodResolver(planSchema),
    defaultValues
  });

  const themeValue = form.watch("theme") || "";

  useEffect(() => {
    const draft = getPlanDraft();
    if (draft) {
      form.reset({ ...defaultValues, ...draft });
    }
  }, [form]);

  const planMutation = useMutation({
    onMutate: (values: PlanFormValues) => {
      savePlanDraft(values);
      setRequestSnapshot(buildRequestSnapshot(values));
      setLatestResponse(null);
      setLatestItinerary(null);
    },
    mutationFn: async (values: PlanFormValues) => apiClient.plan(buildStructuredPlanPayload(values)),
    onSuccess: (response, variables) => {
      setLatestResponse(response);
      setLatestItinerary(response.itinerary ?? null);
      addHistory(variables, response);
      toast.success("行程生成成功");
    },
    onError: (error) => {
      setLatestResponse(null);
      setLatestItinerary(null);
      toast.error(toUserMessage(error));
    }
  });

  const dailyCost = useMemo(() => {
    if (!latestItinerary || latestItinerary.days.length === 0) {
      return 0;
    }
    return latestItinerary.total_cost / latestItinerary.days.length;
  }, [latestItinerary]);

  const displayedMessage = useMemo(
    () => formatAssistantMessage(latestResponse?.message, Boolean(latestItinerary)),
    [latestItinerary, latestResponse?.message]
  );

  const requestSummary = useMemo(() => {
    if (!requestSnapshot) {
      return "";
    }
    const parts = [`本次请求：${requestSnapshot.city} · ${requestSnapshot.days}天`];
    if (requestSnapshot.budget_per_day) {
      parts.push(`预算目标 ${requestSnapshot.budget_per_day} 元/天`);
    }
    if (requestSnapshot.date_start || requestSnapshot.date_end) {
      parts.push(`日期 ${requestSnapshot.date_start || "未填"} ~ ${requestSnapshot.date_end || "未填"}`);
    }
    return parts.join(" · ");
  }, [requestSnapshot]);

  const dateMismatchWarning = useMemo(() => {
    if (!requestSnapshot || !latestItinerary?.days?.length) {
      return "";
    }
    const requestedStart = normalizeDate(requestSnapshot.date_start);
    if (!requestedStart) {
      return "";
    }
    const firstDayWithDate = latestItinerary.days.find((day) => Boolean(day.date));
    const itineraryStart = normalizeDate(firstDayWithDate?.date);
    if (!itineraryStart || itineraryStart === requestedStart) {
      return "";
    }
    return `你选择 ${requestedStart} 出发，但结果从 ${itineraryStart} 开始。请重试，或检查后端日期约束是否生效。`;
  }, [latestItinerary, requestSnapshot]);

  const handleCopyJson = async () => {
    if (!latestItinerary) {
      return;
    }
    await navigator.clipboard.writeText(JSON.stringify(latestItinerary, null, 2));
    toast.success("已复制 JSON");
  };

  const handleCopyMarkdown = async () => {
    if (!latestItinerary) {
      return;
    }
    await navigator.clipboard.writeText(itineraryToMarkdown(latestItinerary));
    toast.success("已复制 Markdown");
  };

  const handleDownloadJson = () => {
    if (!latestItinerary) {
      return;
    }
    const blob = new Blob([JSON.stringify(latestItinerary, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `trip-plan-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success("已下载 JSON 文件");
  };

  const addTheme = (theme: string) => {
    const existing = splitThemes(themeValue);
    if (existing.includes(theme)) {
      form.setValue(
        "theme",
        existing.filter((item) => item !== theme).join("、"),
        { shouldDirty: true }
      );
      return;
    }
    form.setValue("theme", [...existing, theme].join("、"), { shouldDirty: true });
  };

  const setBudget = (budget: number) => {
    form.setValue("budget", budget, { shouldDirty: true });
  };

  const applyPreset = (preset: {
    days: number;
    pace: Pace;
    travelers: TravelersType;
    transport: TransportMode;
    budget: number;
  }) => {
    form.setValue("days", preset.days, { shouldDirty: true });
    form.setValue("pace", preset.pace, { shouldDirty: true });
    form.setValue("travelers", preset.travelers, { shouldDirty: true });
    form.setValue("transport", preset.transport, { shouldDirty: true });
    form.setValue("budget", preset.budget, { shouldDirty: true });
    toast.success("已应用模板，请补充城市后生成");
  };

  const selectedThemes = themeValue ? splitThemes(themeValue) : [];

  return (
    <main className="page-container space-y-6">
      <div>
        <h1 className="page-title">智能行程规划</h1>
        <p className="page-subtitle">按国内用户常用习惯填写偏好，一键生成可执行的旅行路线。</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>常用出行模板</CardTitle>
          <CardDescription>先选模板，再补充城市和个性化要求，效率更高。</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          {planPresets.map((preset) => (
            <button
              key={preset.label}
              type="button"
              className="rounded-md border p-3 text-left transition-colors hover:bg-muted"
              onClick={() => applyPreset(preset.values)}
            >
              <p className="text-sm font-semibold">{preset.label}</p>
              <p className="mt-1 text-xs text-muted-foreground">{preset.description}</p>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>规划表单</CardTitle>
          <CardDescription>字段会自动拼接成后端可识别的自然语言请求。</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4 md:grid-cols-2"
            onSubmit={form.handleSubmit((values) => planMutation.mutate(values))}
          >
            <Field label="出发城市" error={form.formState.errors.city?.message}>
              <Input
                data-testid="plan-city-input"
                placeholder="例如：北京、上海、成都"
                {...form.register("city")}
              />
            </Field>

            <Field label="旅行天数" error={form.formState.errors.days?.message}>
              <Input
                data-testid="plan-days-input"
                type="number"
                min={1}
                max={14}
                {...form.register("days", { valueAsNumber: true })}
              />
            </Field>

            <div className="space-y-1.5">
              <Label>预算（每天）</Label>
              <Input type="number" min={0} placeholder="例如：500" {...form.register("budget", { valueAsNumber: true })} />
              <div className="flex flex-wrap gap-2">
                {budgetSuggestions.map((budget) => (
                  <button
                    key={budget}
                    type="button"
                    className="rounded-full border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                    onClick={() => setBudget(budget)}
                  >
                    {budget} 元
                  </button>
                ))}
              </div>
            </div>

            <Field label="出游节奏">
              <Select {...form.register("pace")}>
                {Object.entries(paceLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="space-y-1.5 md:col-span-2">
              <Label>主题偏好</Label>
              <Input placeholder="例如：历史古迹、夜景、美食夜市" {...form.register("theme")} />
              <div className="flex flex-wrap gap-2">
                {themeSuggestions.map((theme) => {
                  const selected = selectedThemes.includes(theme);
                  return (
                    <button
                      key={theme}
                      type="button"
                      className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs ${
                        selected ? "border-primary bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted"
                      }`}
                      onClick={() => addTheme(theme)}
                    >
                      {selected ? <Check className="h-3 w-3" /> : null}
                      {theme}
                    </button>
                  );
                })}
              </div>
            </div>

            <Field label="交通方式">
              <Select {...form.register("transport")}>
                {Object.entries(transportLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="出行人群">
              <Select {...form.register("travelers")}>
                {Object.entries(travelerLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="出发日期">
                <Input type="date" {...form.register("date_start")} />
              </Field>
              <Field label="返程日期">
                <Input type="date" {...form.register("date_end")} />
              </Field>
            </div>

            <div className="md:col-span-2">
              <Field label="补充要求">
                <Textarea
                  placeholder="例如：希望中午留出午休时间；周末人多的景点安排在工作日"
                  {...form.register("extraNotes")}
                />
              </Field>
            </div>

            <div className="md:col-span-2 flex flex-wrap items-center gap-3">
              <Button data-testid="plan-submit-btn" type="submit" disabled={planMutation.isPending}>
                {planMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    正在生成...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    一键生成行程
                  </>
                )}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  form.reset(defaultValues);
                  savePlanDraft(defaultValues);
                }}
              >
                重置表单
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {planMutation.isPending ? (
        <Card>
          <CardHeader>
            <CardTitle>生成中</CardTitle>
            <CardDescription>正在分析偏好、计算路线、组织行程文案。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </CardContent>
        </Card>
      ) : null}

      {displayedMessage ? <Alert data-testid="plan-result-alert">{displayedMessage}</Alert> : null}
      {requestSummary && (planMutation.isPending || latestItinerary) ? <Alert>{requestSummary}</Alert> : null}
      {dateMismatchWarning ? <Alert variant="destructive">{dateMismatchWarning}</Alert> : null}

      {latestItinerary ? (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>导出与复用</CardTitle>
              <CardDescription>
                共 {latestItinerary.days.length} 天 · 总成本 {latestItinerary.total_cost} · 日均{" "}
                {Number.isFinite(dailyCost) ? dailyCost.toFixed(0) : 0}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={handleCopyMarkdown}>
                <Copy className="mr-2 h-4 w-4" />
                复制 Markdown
              </Button>
              <Button variant="secondary" onClick={handleCopyJson}>
                <Copy className="mr-2 h-4 w-4" />
                复制 JSON
              </Button>
              <Button variant="outline" onClick={handleDownloadJson}>
                <Download className="mr-2 h-4 w-4" />
                下载 JSON
              </Button>
            </CardContent>
          </Card>
          <div data-testid="plan-itinerary-renderer">
            <ItineraryRenderer
              itinerary={latestItinerary}
              requestedBudgetPerDay={requestSnapshot?.budget_per_day}
            />
          </div>
        </div>
      ) : null}
    </main>
  );
}

function Field({
  label,
  error,
  children
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
