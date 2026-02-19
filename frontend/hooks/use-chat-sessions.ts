"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getChatSessions, saveChatSessions } from "@/lib/storage";
import type { ChatMessage, ChatSession } from "@/lib/types/api";
import { randomId } from "@/lib/utils";

function createSession(): ChatSession {
  const now = new Date().toISOString();
  return {
    id: randomId("session"),
    title: "新会话",
    createdAt: now,
    updatedAt: now,
    messages: []
  };
}

export function useChatSessions() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string>("");

  useEffect(() => {
    const loaded = getChatSessions();
    if (loaded.length === 0) {
      const fallback = createSession();
      setSessions([fallback]);
      setActiveId(fallback.id);
      saveChatSessions([fallback]);
      return;
    }
    setSessions(loaded);
    setActiveId(loaded[0].id);
  }, []);

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeId) ?? sessions[0] ?? null,
    [activeId, sessions]
  );

  const createNewSession = useCallback(() => {
    const session = createSession();
    setSessions((prev) => {
      const next = [session, ...prev];
      saveChatSessions(next);
      return next;
    });
    setActiveId(session.id);
  }, []);

  const appendMessage = useCallback((sessionId: string, message: ChatMessage) => {
    setSessions((prev) => {
      const next = prev.map((session) => {
        if (session.id !== sessionId) {
          return session;
        }
        const title =
          session.title === "新会话" && message.role === "user"
            ? message.content.slice(0, 20) || "新会话"
            : session.title;
        return {
          ...session,
          title,
          updatedAt: new Date().toISOString(),
          messages: [...session.messages, message]
        };
      });
      saveChatSessions(next);
      return next;
    });
  }, []);

  const deleteSession = useCallback((sessionId: string) => {
    setSessions((prev) => {
      const next = prev.filter((session) => session.id !== sessionId);
      if (next.length === 0) {
        const fallback = createSession();
        saveChatSessions([fallback]);
        setActiveId(fallback.id);
        return [fallback];
      }
      if (activeId === sessionId) {
        setActiveId(next[0].id);
      }
      saveChatSessions(next);
      return next;
    });
  }, [activeId]);

  return {
    sessions,
    activeId,
    setActiveId,
    activeSession,
    createNewSession,
    appendMessage,
    deleteSession
  };
}
