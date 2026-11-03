"use client";

import { useState } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { Empty, Notice, PageHead, useLoad } from "@/components/ui";
import { api } from "@/lib/api";
import { ACTION_LABELS, fmtDate } from "@/lib/format";
import type { ApprovalStatus } from "@/lib/types";

const FILTERS: { value: ApprovalStatus | ""; label: string }[] = [
  { value: "pending", label: "Waiting" },
  { value: "executed", label: "Sent" },
  { value: "failed", label: "Failed" },
  { value: "rejected", label: "Rejected" },
  { value: "expired", label: "Expired" },
  { value: "", label: "All" },
];

export default function ApprovalsPage() {
  const [filter, setFilter] = useState<ApprovalStatus | "">("pending");
  const { data, error, loading, reload } = useLoad(() => api.approvals(filter || undefined), [filter]);

  return (
    <section>
      <PageHead eyebrow="APPROVALS" title="Nothing leaves without your OK">
        <button type="button" className="ghost" onClick={() => void reload()}>
          Refresh
        </button>
      </PageHead>
      <p className="muted">
        Every email, LinkedIn post or message to another person shows up here first, exactly as it will be sent. Approving sends that exact content; any edit creates a new preview.
      </p>
      <div className="filters">
        {FILTERS.map((f) => (
          <button key={f.label} type="button" className={filter === f.value ? "chip active" : "chip"} onClick={() => setFilter(f.value)}>
            {f.label}
          </button>
        ))}
      </div>
      <Notice kind="error">{error}</Notice>
      {loading && <p className="loading">Loading…</p>}
      {!loading && data?.length === 0 && <Empty>Nothing here.</Empty>}
      <div className="list">
        {data?.map((a) =>
          a.status === "pending" || a.status === "failed" || (a.status === "executed" && a.result?.delivery === "manual") ? (
            <ApprovalCard key={a.id} approval={a} onChange={() => void reload()} />
          ) : (
            <article className="item compact" key={a.id}>
              <div className="item-head">
                <div>
                  <h3>
                    {ACTION_LABELS[a.action_type] ?? a.action_type}
                    {a.subject ? `: ${a.subject}` : ""}
                  </h3>
                  <p className="muted small">
                    {a.channel}
                    {a.destination?.to ? ` → ${a.destination.to.join(", ")}` : ""} · created {fmtDate(a.created_at, true)}
                    {a.executed_at ? ` · sent ${fmtDate(a.executed_at, true)}` : ""}
                  </p>
                </div>
                <span className={`badge badge-${a.status}`}>{a.status}</span>
              </div>
              <details>
                <summary>Show content</summary>
                <pre className="approval-body">{a.body}</pre>
              </details>
            </article>
          ),
        )}
      </div>
    </section>
  );
}
