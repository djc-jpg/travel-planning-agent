import { expect, test } from "@playwright/test";

const itineraryPayload = {
  city: "北京",
  days: [
    {
      day_number: 1,
      date: "2026-04-01",
      schedule: [
        {
          poi: {
            id: "poi_1",
            name: "故宫博物院",
            city: "北京",
            lat: 39.9163,
            lon: 116.3972,
            themes: ["历史古迹"],
            duration_hours: 2.5,
            cost: 60,
            indoor: false,
            description: "明清皇家宫殿",
            ticket_price: 60,
            reservation_required: true,
            closed_rules: "周一闭馆"
          },
          time_slot: "morning",
          travel_minutes: 20,
          notes: "核心景点",
          is_backup: false
        }
      ],
      backups: [],
      day_summary: "历史文化路线",
      estimated_cost: 260,
      total_travel_minutes: 40
    }
  ],
  total_cost: 520,
  assumptions: [],
  summary: "北京2日历史轻松游"
};

test("plan page key flow: submit form and render itinerary", async ({ page }) => {
  await page.route("**/api/backend/plan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "done",
        message: "行程已生成，可在下方查看每天安排。",
        itinerary: itineraryPayload,
        session_id: "sess_1",
        request_id: "req_1",
        trace_id: "trace_1",
        degrade_level: "L1"
      })
    });
  });

  await page.goto("/");
  await page.getByTestId("plan-city-input").fill("北京");
  await page.getByTestId("plan-days-input").fill("2");
  await page.getByTestId("plan-submit-btn").click();

  await expect(page.getByTestId("plan-result-alert")).toBeVisible();
  await expect(page.getByTestId("plan-itinerary-renderer")).toBeVisible();
  await expect(page.getByText("故宫博物院")).toBeVisible();
});

test("chat page key flow: send message and receive itinerary", async ({ page }) => {
  await page.route("**/api/backend/chat", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "done",
        message: "已根据你的需求调整行程。",
        itinerary: itineraryPayload,
        session_id: "chat_1",
        request_id: "req_chat_1",
        trace_id: "trace_chat_1",
        degrade_level: "L1"
      })
    });
  });

  await page.goto("/chat");
  await page.getByTestId("chat-input").fill("第二天想安排历史景点和夜景");
  await page.getByTestId("chat-send-btn").click();

  await expect(page.locator("p.whitespace-pre-wrap", { hasText: "第二天想安排历史景点和夜景" })).toBeVisible();
  await expect(page.getByTestId("chat-itinerary-renderer")).toBeVisible();
  await expect(page.getByText("故宫博物院")).toBeVisible();
});

test("history page key flow: query session and load export", async ({ page }) => {
  await page.route("**/api/backend/sessions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            session_id: "session_1",
            updated_at: "2026-04-01T08:00:00Z",
            last_status: "done",
            last_trace_id: "trace_1"
          }
        ]
      })
    });
  });

  await page.route("**/api/backend/sessions/session_1/history?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: "session_1",
        items: [
          {
            request_id: "req_1",
            trace_id: "trace_1",
            message: "北京2天历史游",
            status: "done",
            degrade_level: "L1",
            confidence_score: 0.9,
            run_fingerprint: { run_mode: "DEGRADED" },
            created_at: "2026-04-01T08:00:00Z"
          }
        ]
      })
    });
  });

  await page.route("**/api/backend/plans/req_1/export", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        request_id: "req_1",
        session_id: "session_1",
        trace_id: "trace_1",
        message: "北京2天历史游",
        constraints: { city: "北京", days: 2 },
        user_profile: { themes: ["历史古迹"] },
        metadata: {},
        status: "done",
        degrade_level: "L1",
        confidence_score: 0.9,
        run_fingerprint: { run_mode: "DEGRADED" },
        itinerary: itineraryPayload,
        issues: [],
        next_questions: [],
        field_evidence: {},
        metrics: { verified_fact_ratio: 0.9 },
        created_at: "2026-04-01T08:00:00Z",
        artifacts: []
      })
    });
  });

  await page.goto("/history");
  await page.getByTestId("history-recent-session_1").click();
  await page.getByTestId("history-load-export-req_1").click();
  await expect(page.getByTestId("history-export-details")).toBeVisible();
  await expect(page.getByText("request_id: req_1")).toBeVisible();
});
