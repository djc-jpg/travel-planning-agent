"use client";

import { useCallback, useEffect, useState } from "react";

import { getPlanHistory, savePlanHistory } from "@/lib/storage";
import type { PlanFormValues, PlanResponse, StoredPlanHistory } from "@/lib/types/api";
import { randomId } from "@/lib/utils";

export function usePlanHistory() {
  const [history, setHistory] = useState<StoredPlanHistory[]>([]);

  useEffect(() => {
    setHistory(getPlanHistory());
  }, []);

  const addHistory = useCallback((request: PlanFormValues, response: PlanResponse) => {
    setHistory((prev) => {
      const next = [{ id: randomId("plan"), createdAt: new Date().toISOString(), request, response }, ...prev].slice(
        0,
        10
      );
      savePlanHistory(next);
      return next;
    });
  }, []);

  const removeHistory = useCallback((id: string) => {
    setHistory((prev) => {
      const next = prev.filter((item) => item.id !== id);
      savePlanHistory(next);
      return next;
    });
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    savePlanHistory([]);
  }, []);

  return {
    history,
    addHistory,
    removeHistory,
    clearHistory
  };
}
