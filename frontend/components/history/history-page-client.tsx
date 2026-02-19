"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { ItineraryRenderer } from "@/components/itinerary-renderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { usePlanHistory } from "@/hooks/use-plan-history";
import { savePlanDraft } from "@/lib/storage";
import type { StoredPlanHistory } from "@/lib/types/api";

export function HistoryPageClient() {
  const router = useRouter();
  const { history, removeHistory, clearHistory } = usePlanHistory();

  const handleRestore = (item: StoredPlanHistory) => {
    savePlanDraft(item.request);
    toast.success("已恢复到 Plan 表单草稿");
    router.push("/");
  };

  return (
    <main className="page-container space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="page-title">规划历史</h1>
          <p className="page-subtitle">本地保留最近 10 条记录，适合快速复用和对比。</p>
        </div>
        <Button variant="outline" onClick={clearHistory} disabled={history.length === 0}>
          清空历史
        </Button>
      </div>

      {history.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">暂无历史记录，先在 Plan 页面生成一次行程。</p>
          </CardContent>
        </Card>
      ) : (
        history.map((item) => (
          <Card key={item.id}>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                <span>{item.request.city || "未命名城市"}</span>
                <Badge>{item.request.days} 天</Badge>
                <Badge className="bg-secondary text-secondary-foreground">
                  {item.request.budget ? `¥${item.request.budget}/天` : "预算未填"}
                </Badge>
              </CardTitle>
              <CardDescription>
                {new Date(item.createdAt).toLocaleString("zh-CN", { hour12: false })} · 状态 {item.response.status}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => handleRestore(item)}>恢复到 Plan</Button>
                <Button variant="secondary" onClick={() => removeHistory(item.id)}>
                  删除
                </Button>
              </div>
              <Separator />
              {item.response.itinerary ? (
                <ItineraryRenderer itinerary={item.response.itinerary} compact />
              ) : (
                <p className="text-sm text-muted-foreground">{item.response.message || "无 itinerary 返回"}</p>
              )}
            </CardContent>
          </Card>
        ))
      )}
    </main>
  );
}
