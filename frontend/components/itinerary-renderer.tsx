import { AlertTriangle, CalendarDays, Coins, MapPin, Route, Timer } from "lucide-react";

import { timeSlotLabels } from "@/lib/constants";
import { prettifySummary, sanitizeDebugText } from "@/lib/itinerary-text";
import type { Itinerary } from "@/lib/types/api";
import { formatCurrency, formatDate } from "@/lib/utils";

import { Badge } from "./ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

type ItineraryRendererProps = {
  itinerary: Itinerary;
  compact?: boolean;
  requestedBudgetPerDay?: number;
};

type PoiPayload = Itinerary["days"][number]["schedule"][number]["poi"];

const BUDGET_SOURCE_LABEL: Record<string, string> = {
  verified: "已核验",
  curated: "结构化数据",
  heuristic: "估算",
  fallback: "回退值",
  unknown: "未知来源"
};

function budgetConfidenceLabel(score: number): string {
  if (score >= 0.8) {
    return "高";
  }
  if (score >= 0.6) {
    return "中";
  }
  if (score > 0) {
    return "低";
  }
  return "未知";
}

function budgetDeltaText(requestedBudgetPerDay: number, avgDaily: number): string {
  const delta = avgDaily - requestedBudgetPerDay;
  const absDelta = Math.abs(delta);
  const tolerance = requestedBudgetPerDay * 0.1;
  if (absDelta <= tolerance) {
    return `与目标接近（偏差 ${formatCurrency(absDelta)}）`;
  }
  if (delta > 0) {
    return `超出目标约 ${formatCurrency(absDelta)} / 天`;
  }
  return `低于目标约 ${formatCurrency(absDelta)} / 天`;
}

function formatPoiTicketLine(poi: PoiPayload): string {
  const ticketPrice = Number(poi.ticket_price ?? poi.cost ?? 0);
  if (ticketPrice > 0) {
    return `门票约 ${formatCurrency(ticketPrice)}`;
  }

  const sourceType = String(
    poi.fact_sources?.ticket_price_source_type ?? poi.fact_sources?.ticket_price ?? ""
  ).toLowerCase();
  if (sourceType === "verified" || sourceType === "curated") {
    return "门票免费或已含套餐";
  }
  return "门票待确认";
}

export function ItineraryRenderer({
  itinerary,
  compact = false,
  requestedBudgetPerDay
}: ItineraryRendererProps) {
  const dayCount = itinerary.days.length || 1;
  const avgDaily = itinerary.total_cost > 0 ? itinerary.total_cost / dayCount : 0;
  const summary = prettifySummary(itinerary.summary ?? "", itinerary.city, dayCount, itinerary.days);
  const budgetBreakdown = itinerary.budget_breakdown ?? {};
  const budgetSource = itinerary.budget_source_breakdown ?? {};
  const budgetConfidence = itinerary.budget_confidence_breakdown ?? {};
  const budgetRows = [
    {
      key: "tickets",
      label: "门票/体验",
      amount: Number(budgetBreakdown.tickets ?? 0),
      source: String(budgetSource.tickets ?? "unknown"),
      confidence: Number(budgetConfidence.tickets ?? 0)
    },
    {
      key: "local_transport",
      label: "市内交通",
      amount: Number(budgetBreakdown.local_transport ?? 0),
      source: String(budgetSource.local_transport ?? "unknown"),
      confidence: Number(budgetConfidence.local_transport ?? 0)
    },
    {
      key: "food_min",
      label: "餐饮最低",
      amount: Number(budgetBreakdown.food_min ?? 0),
      source: String(budgetSource.food_min ?? "unknown"),
      confidence: Number(budgetConfidence.food_min ?? 0)
    }
  ];
  const totalBudgetConfidence = Number(itinerary.budget_confidence_score ?? 0);
  const budgetAdjustments = (itinerary.assumptions ?? [])
    .map((row) => String(row || "").trim())
    .filter((row) => row.includes("预算优化") || row.includes("棰勭畻浼樺寲"));
  const hasRequestedBudget =
    typeof requestedBudgetPerDay === "number" &&
    Number.isFinite(requestedBudgetPerDay) &&
    requestedBudgetPerDay > 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-primary" />
            {itinerary.city} 行程总览
          </CardTitle>
          <CardDescription>按“每天安排”阅读，支持快速查看预算、交通和重点体验。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-3">
            <OverviewItem icon={CalendarDays} label="行程天数" value={`${dayCount} 天`} />
            <OverviewItem icon={Coins} label="总预算" value={formatCurrency(itinerary.total_cost)} />
            <OverviewItem icon={Timer} label="日均预算" value={formatCurrency(avgDaily)} />
          </div>
          {summary ? (
            <p className="mt-4 rounded-md bg-muted p-3 text-sm text-muted-foreground">{summary}</p>
          ) : null}
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            {budgetRows.map((row) => (
              <div key={row.key} className="rounded-md border bg-background p-3">
                <p className="text-xs text-muted-foreground">{row.label}</p>
                <p className="mt-1 text-sm font-semibold">{formatCurrency(row.amount)}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  来源 {BUDGET_SOURCE_LABEL[row.source] ?? BUDGET_SOURCE_LABEL.unknown} · 可信度 {budgetConfidenceLabel(row.confidence)}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            预算可信度：{budgetConfidenceLabel(totalBudgetConfidence)}（{Math.round(totalBudgetConfidence * 100)}%）
            {itinerary.budget_as_of ? ` · 数据日期 ${itinerary.budget_as_of}` : ""}
          </p>
          {hasRequestedBudget ? (
            <p className="mt-1 text-xs text-muted-foreground">
              预算目标 {formatCurrency(requestedBudgetPerDay ?? 0)} / 天 · 估算 {formatCurrency(avgDaily)} / 天 · {budgetDeltaText(requestedBudgetPerDay ?? 0, avgDaily)}
            </p>
          ) : null}
          {itinerary.budget_warning ? (
            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              <AlertTriangle className="mr-1 inline h-4 w-4" />
              {itinerary.budget_warning}
            </div>
          ) : null}
          {budgetAdjustments.length > 0 ? (
            <div className="mt-3 rounded-md border bg-muted p-3">
              <p className="text-xs font-medium text-muted-foreground">预算调整</p>
              <div className="mt-2 space-y-1">
                {budgetAdjustments.map((row, idx) => (
                  <p key={`${row}-${idx}`} className="text-xs text-muted-foreground">
                    {row}
                  </p>
                ))}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {itinerary.days.map((day) => {
        const daySummary = sanitizeDebugText(day.day_summary);
        return (
          <Card key={`${day.day_number}-${day.date ?? "nodate"}`}>
            <CardHeader className={compact ? "pb-2" : undefined}>
              <CardTitle className="text-base">
                第{day.day_number}天 · {formatDate(day.date)}
              </CardTitle>
              <CardDescription>
                预计花费 {formatCurrency(day.estimated_cost)} · 交通总时长 {Math.round(day.total_travel_minutes)} 分钟
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {day.schedule.length === 0 ? (
                <p className="text-sm text-muted-foreground">当天暂无景点安排。</p>
              ) : (
                day.schedule.map((item) => {
                  const note = sanitizeDebugText(item.notes);
                  return (
                    <div key={`${item.poi.id}-${item.start_time ?? item.time_slot}`} className="rounded-md border p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium">{item.poi.name}</p>
                          {item.is_backup ? (
                            <Badge className="bg-amber-100 text-amber-800">备选</Badge>
                          ) : null}
                        </div>
                        <Badge>{timeSlotLabels[item.time_slot]}</Badge>
                      </div>

                      <p className="mt-1 text-xs text-muted-foreground">
                        {item.start_time ?? "--:--"} - {item.end_time ?? "--:--"} · {formatPoiTicketLine(item.poi)}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        <Route className="mr-1 inline h-3 w-3" />
                        交通约 {Math.round(item.travel_minutes)} 分钟
                      </p>

                      {item.poi.themes.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {item.poi.themes.slice(0, 4).map((theme) => (
                            <Badge key={`${item.poi.id}-${theme}`} className="bg-secondary">
                              {theme}
                            </Badge>
                          ))}
                        </div>
                      ) : null}

                      {note ? <p className="mt-2 text-sm text-muted-foreground">{note}</p> : null}
                    </div>
                  );
                })
              )}

              {daySummary ? (
                <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">{daySummary}</p>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function OverviewItem({
  icon: Icon,
  label,
  value
}: {
  icon: typeof CalendarDays;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border bg-background p-3">
      <p className="text-xs text-muted-foreground">
        <Icon className="mr-1 inline h-3 w-3" />
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}
