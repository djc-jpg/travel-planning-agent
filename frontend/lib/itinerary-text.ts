import type { ItineraryDay } from "@/lib/types/api";

const NOTE_DEBUG_PREFIXES = ["cluster=", "buffer=", "routing_confidence=", "closed_rules="];
const NOTE_DEBUG_EXACT = new Set(["avoid_peak_hours", "fallback_schedule", "backup_option"]);
const MACHINE_SUMMARY_HINTS = /(executable itinerary|day\d+\s*:)/i;
const MACHINE_MESSAGE_HINTS = /(executable itinerary|day\d+\s*:|cluster=|routing_confidence=)/i;

function splitNoteParts(text: string): string[] {
  return String(text)
    .split(/[|｜]/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function sanitizeDebugText(text?: string | null): string {
  if (!text) {
    return "";
  }
  const visible: string[] = [];
  for (const part of splitNoteParts(text)) {
    const lowered = part.toLowerCase();
    if (NOTE_DEBUG_EXACT.has(lowered)) {
      continue;
    }
    if (NOTE_DEBUG_PREFIXES.some((prefix) => lowered.startsWith(prefix))) {
      continue;
    }
    visible.push(part);
  }
  return visible.join(" | ").replace(/\s+/g, " ").trim();
}

function summaryFromMachineText(summary: string): string[] {
  const rows: string[] = [];
  for (const match of summary.matchAll(/day\s*(\d+)\s*:\s*([^;|]+)/gi)) {
    const day = Number(match[1]);
    const names = match[2]
      .split("->")
      .map((item) => item.trim())
      .filter(Boolean)
      .join("、");
    if (Number.isFinite(day) && names) {
      rows.push(`第${day}天：${names}`);
    }
  }
  return rows;
}

function summaryFromDays(days: ItineraryDay[] | undefined): string[] {
  if (!Array.isArray(days)) {
    return [];
  }
  return days
    .slice(0, 3)
    .map((day) => {
      const names = day.schedule
        .slice(0, 3)
        .map((item) => item.poi.name)
        .filter(Boolean)
        .join("、");
      return names ? `第${day.day_number}天：${names}` : "";
    })
    .filter(Boolean);
}

export function prettifySummary(
  summary: string | undefined,
  city: string,
  dayCount: number,
  days?: ItineraryDay[]
): string {
  const cleaned = sanitizeDebugText(summary ?? "");
  if (cleaned && !MACHINE_SUMMARY_HINTS.test(cleaned)) {
    return cleaned;
  }

  const rows = cleaned ? summaryFromMachineText(cleaned) : [];
  if (rows.length) {
    return `${city}${dayCount}天行程亮点：${rows.join("；")}`;
  }

  const rowsFromDays = summaryFromDays(days);
  if (rowsFromDays.length) {
    return `${city}${dayCount}天行程亮点：${rowsFromDays.join("；")}`;
  }

  return `${city}${dayCount}天行程已生成，可按“每天安排”执行。`;
}

export function formatAssistantMessage(message: string | undefined, hasItinerary: boolean): string {
  const cleaned = sanitizeDebugText(message ?? "");
  if (!cleaned) {
    return hasItinerary ? "行程已生成，可在下方查看每天安排。" : "";
  }
  if (MACHINE_MESSAGE_HINTS.test(cleaned)) {
    return hasItinerary ? "行程已生成，可在下方查看每天安排。" : "已收到需求，正在生成行程。";
  }
  return cleaned;
}
