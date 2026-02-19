import type { Pace, TimeSlot, TransportMode, TravelersType } from "@/lib/types/api";

export const paceLabels: Record<Pace, string> = {
  relaxed: "轻松慢游",
  moderate: "经典平衡",
  intensive: "高效打卡"
};

export const transportLabels: Record<TransportMode, string> = {
  walking: "步行优先",
  public_transit: "公共交通",
  taxi: "打车出行",
  driving: "自驾"
};

export const travelerLabels: Record<TravelersType, string> = {
  solo: "独自出行",
  couple: "情侣",
  family: "亲子家庭",
  friends: "朋友结伴",
  elderly: "长辈同行"
};

export const timeSlotLabels: Record<TimeSlot, string> = {
  morning: "上午",
  lunch: "午间",
  afternoon: "下午",
  dinner: "傍晚",
  evening: "夜间"
};

export const themeSuggestions = [
  "历史古迹",
  "博物馆",
  "网红拍照",
  "自然风光",
  "城市地标",
  "亲子体验",
  "美食夜市",
  "咖啡文艺",
  "购物休闲",
  "夜景灯光"
];

export const budgetSuggestions = [300, 500, 800, 1200];

export const planPresets = [
  {
    label: "周末轻松游",
    description: "2天，轻松节奏，适合情侣/朋友",
    values: {
      days: 2,
      pace: "relaxed" as Pace,
      travelers: "couple" as TravelersType,
      transport: "public_transit" as TransportMode,
      budget: 500
    }
  },
  {
    label: "亲子舒适游",
    description: "3天，室内外均衡，行程不过载",
    values: {
      days: 3,
      pace: "relaxed" as Pace,
      travelers: "family" as TravelersType,
      transport: "taxi" as TransportMode,
      budget: 800
    }
  },
  {
    label: "深度文化游",
    description: "4天，中等节奏，历史人文优先",
    values: {
      days: 4,
      pace: "moderate" as Pace,
      travelers: "friends" as TravelersType,
      transport: "public_transit" as TransportMode,
      budget: 700
    }
  },
  {
    label: "高效打卡游",
    description: "3天，热门景点覆盖更全面",
    values: {
      days: 3,
      pace: "intensive" as Pace,
      travelers: "friends" as TravelersType,
      transport: "taxi" as TransportMode,
      budget: 1000
    }
  }
];

export const chatQuickPrompts = [
  "把行程改成4天，预算每天700",
  "优先室内景点，减少步行",
  "加上本地人常去的美食",
  "第三天改成亲子路线",
  "整体节奏放慢一点"
];
