"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { Notice, PageHead } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Approval, ChatMessage } from "@/lib/types";

interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  approvals: Approval[];
}

const SUGGESTIONS = [
  "Find backend jobs in Bengaluru or remote",
  "Show my best matches",
  "What follow-ups are due this week?",
  "Draft a thank-you email for my last interview",
];

export default function ChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .chatHistory()
      .then((rows: ChatMessage[]) =>
        setTurns(rows.filter((r) => r.role === "user" || r.role === "assistant").map((r) => ({ id: r.id, role: r.role as Turn["role"], content: r.content, approvals: [] }))),
      )
      .catch((err) => setError(errorMessage(err)));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    setText("");
    setTurns((t) => [...t, { id: `u${Date.now()}`, role: "user", content: trimmed, approvals: [] }]);
    try {
      const resp = await api.chat(trimmed);
      setTurns((t) => [...t, { id: `a${Date.now()}`, role: "assistant", content: resp.reply, approvals: resp.approvals }]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(text);
  }

  return (
    <section className="chat">
      <PageHead eyebrow="ASSISTANT" title="What should we work on?">
        <Link className="ghost-link" href="/app/approvals">
          Pending approvals
        </Link>
      </PageHead>
      <Notice kind="info">I can search and draft on my own. Anything that goes to another person waits for your approval below.</Notice>
      <div className="chat-log" aria-live="polite">
        {turns.length === 0 && (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" className="ghost" onClick={() => void send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {turns.map((turn) => (
          <div key={turn.id} className={`bubble bubble-${turn.role}`}>
            <p>{turn.content}</p>
            {turn.approvals.map((a) => (
              <ApprovalCard key={a.id} approval={a} />
            ))}
          </div>
        ))}
        {busy && <div className="bubble bubble-assistant typing">Thinking…</div>}
        <div ref={endRef} />
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      <form className="chat-input" onSubmit={onSubmit}>
        <textarea
          rows={2}
          placeholder="Ask about jobs, applications, emails…"
          value={text}
          maxLength={4000}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(text);
            }
          }}
        />
        <button type="submit" disabled={busy || !text.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
