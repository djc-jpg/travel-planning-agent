import { paceLabels, timeSlotLabels, transportLabels, travelerLabels } from "@/lib/constants";
import type { Itinerary, PlanFormValues } from "@/lib/types/api";

export function buildPlanMessage(values: PlanFormValues): string {
  const parts: string[] = [];
  parts.push(`我想去${values.city}玩${values.days}天`);
  if (values.budget) {
    parts.push(`预算每天${values.budget}元`);
  }
  parts.push(`节奏偏好是${paceLabels[values.pace]}`);
  if (values.theme.trim()) {
    parts.push(`主题偏好是${values.theme.trim()}`);
  }
  parts.push(`交通方式是${transportLabels[values.transport]}`);
  parts.push(`出行人群是${travelerLabels[values.travelers]}`);
  if (values.date_start) {
    parts.push(`开始日期是${values.date_start}`);
  }
  if (values.date_end) {
    parts.push(`结束日期是${values.date_end}`);
  }
  if (values.extraNotes?.trim()) {
    parts.push(`补充要求：${values.extraNotes.trim()}`);
  }
  return `${parts.join("，")}。请生成详细、可执行、适合中国游客习惯的行程安排。`;
}

export function itineraryToMarkdown(itinerary: Itinerary): string {
  const lines: string[] = [];
  lines.push(`# ${itinerary.city} 行程`);
  lines.push("");
  lines.push(`- 天数: ${itinerary.days.length}`);
  lines.push(`- 总成本: ${itinerary.total_cost}`);
  lines.push("");
  for (const day of itinerary.days) {
    lines.push(`## 第 ${day.day_number} 天 ${day.date ?? ""}`.trim());
    lines.push(`- 预估花费: ${day.estimated_cost}`);
    lines.push(`- 交通总时长: ${day.total_travel_minutes} 分钟`);
    for (const item of day.schedule) {
      lines.push(
        `- ${timeSlotLabels[item.time_slot]} | ${item.poi.name} | ${item.poi.cost} 元 | 交通 ${item.travel_minutes} 分钟`
      );
      if (item.notes) {
        lines.push(`  - 备注: ${item.notes}`);
      }
    }
    if (day.day_summary) {
      lines.push(`- 当日总结: ${day.day_summary}`);
    }
    lines.push("");
  }
  if (itinerary.summary) {
    lines.push("## 总结");
    lines.push(itinerary.summary);
  }
  return lines.join("\n");
}

export function inferDraftFromItinerary(itinerary: Itinerary): Partial<PlanFormValues> {
  const dayCount = itinerary.days.length || 3;
  const budget = dayCount > 0 ? Math.ceil((itinerary.total_cost || 0) / dayCount) : undefined;
  return {
    city: itinerary.city,
    days: dayCount,
    budget
  };
}

export function inferDraftFromText(text: string): Partial<PlanFormValues> {
  const result: Partial<PlanFormValues> = {};
  const daysMatch = text.match(/(\d+)\s*天/);
  const budgetMatch = text.match(/预算(?:每天)?\s*(\d+)/);
  const cityMatch = text.match(/去?([\u4e00-\u9fa5]{2,8})(?:玩|旅游|出差|度假)?/);

  if (daysMatch) {
    result.days = Number(daysMatch[1]);
  }
  if (budgetMatch) {
    result.budget = Number(budgetMatch[1]);
  }
  if (cityMatch) {
    result.city = cityMatch[1];
  }
  return result;
}
