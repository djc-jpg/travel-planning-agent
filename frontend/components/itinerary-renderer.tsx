import { CalendarDays, Coins, MapPin, Route, Timer } from "lucide-react";

import { timeSlotLabels } from "@/lib/constants";
import type { Itinerary } from "@/lib/types/api";
import { formatCurrency, formatDate } from "@/lib/utils";

import { Badge } from "./ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

type ItineraryRendererProps = {
  itinerary: Itinerary;
  compact?: boolean;
};

export function ItineraryRenderer({ itinerary, compact = false }: ItineraryRendererProps) {
  const dayCount = itinerary.days.length || 1;
  const avgDaily = itinerary.total_cost > 0 ? itinerary.total_cost / dayCount : 0;

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
          {itinerary.summary ? (
            <p className="mt-4 rounded-md bg-muted p-3 text-sm text-muted-foreground">{itinerary.summary}</p>
          ) : null}
        </CardContent>
      </Card>

      {itinerary.days.map((day) => (
        <Card key={`${day.day_number}-${day.date ?? "nodate"}`}>
          <CardHeader className={compact ? "pb-2" : undefined}>
            <CardTitle className="text-base">
              第 {day.day_number} 天 · {formatDate(day.date)}
            </CardTitle>
            <CardDescription>
              预计花费 {formatCurrency(day.estimated_cost)} · 交通总时长 {Math.round(day.total_travel_minutes)} 分钟
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {day.schedule.length === 0 ? (
              <p className="text-sm text-muted-foreground">当天暂无景点安排。</p>
            ) : (
              day.schedule.map((item) => (
                <div key={`${item.poi.id}-${item.start_time ?? item.time_slot}`} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{item.poi.name}</p>
                      {item.is_backup ? <Badge className="bg-amber-100 text-amber-800">备选</Badge> : null}
                    </div>
                    <Badge>{timeSlotLabels[item.time_slot]}</Badge>
                  </div>

                  <p className="mt-1 text-xs text-muted-foreground">
                    {item.start_time ?? "--:--"} - {item.end_time ?? "--:--"} · 人均约{" "}
                    {formatCurrency(item.poi.cost)}
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

                  {item.notes ? <p className="mt-2 text-sm text-muted-foreground">{item.notes}</p> : null}
                </div>
              ))
            )}

            {day.day_summary ? (
              <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">{day.day_summary}</p>
            ) : null}
          </CardContent>
        </Card>
      ))}
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
