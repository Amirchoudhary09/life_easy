"use client";

import { useState } from "react";

import { api, errorMessage } from "@/lib/api";
import { ACTION_LABELS, fmtDate } from "@/lib/format";
import type { Approval } from "@/lib/types";

/**
 * The approval gate in the UI. Shows exactly what will be sent (channel, destination, full text,
 * attachments) and the content hash the approval binds to. Approve sends that hash; if the
 * content changed on the server, the API refuses. Editing creates a new approval.
 */
export function ApprovalCard({ approval, onChange }: { approval: Approval; onChange?: (next: Approval) => void }) {
  const [current, setCurrent] = useState(approval);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftSubject, setDraftSubject] = useState(approval.subject ?? "");
  const [draftBody, setDraftBody] = useState(approval.body);

  const update = (next: Approval) => {
    setCurrent(next);
    onChange?.(next);
  };

  async function run(fn: () => Promise<Approval>) {
    setBusy(true);
    setError(null);
    try {
      update(await fn());
      setEditing(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const d = current.destination ?? {};
  const pending = current.status === "pending";
  const manualText = current.status === "executed" && current.result?.delivery === "manual" ? String(current.result.text ?? current.body) : null;

  return (
    <article className={`approval approval-${current.status}`}>
      <header className="approval-head">
        <div>
          <span className="eyebrow">{ACTION_LABELS[current.action_type] ?? current.action_type}</span>
          <h3>{pending ? "Waiting for your approval" : `Status: ${current.status}`}</h3>
        </div>
        <span className={`badge badge-${current.status}`}>{current.status}</span>
      </header>

      <dl className="approval-meta">
        <dt>Channel</dt>
        <dd>{current.channel}</dd>
        {d.from && (
          <>
            <dt>From</dt>
            <dd>{d.from}</dd>
          </>
        )}
        {d.to && d.to.length > 0 && (
          <>
            <dt>To</dt>
            <dd>{d.to.join(", ")}</dd>
          </>
        )}
        {d.cc && d.cc.length > 0 && (
          <>
            <dt>Cc</dt>
            <dd>{d.cc.join(", ")}</dd>
          </>
        )}
        {d.audience && (
          <>
            <dt>Audience</dt>
            <dd>{d.audience}</dd>
          </>
        )}
        {d.recipient && (
          <>
            <dt>Recipient</dt>
            <dd>{d.recipient}</dd>
          </>
        )}
        {current.subject && !editing && (
          <>
            <dt>Subject</dt>
            <dd>{current.subject}</dd>
          </>
        )}
        {current.attachments.length > 0 && (
          <>
            <dt>Attachments</dt>
            <dd>{current.attachments.map((a) => a.filename ?? a.type ?? "file").join(", ")}</dd>
          </>
        )}
      </dl>

      {editing ? (
        <div className="stack">
          {current.subject !== null && (
            <label>
              Subject
              <input value={draftSubject} onChange={(e) => setDraftSubject(e.target.value)} />
            </label>
          )}
          <label>
            Message
            <textarea rows={10} value={draftBody} onChange={(e) => setDraftBody(e.target.value)} />
          </label>
          <p className="hint">Saving an edit cancels this preview and creates a new one you approve separately.</p>
        </div>
      ) : (
        <pre className="approval-body">{current.body}</pre>
      )}

      <p className="hash" title={current.content_hash}>
        Approval is bound to content hash <code>{current.content_hash.slice(0, 16)}…</code>
        {pending && <> · expires {fmtDate(current.expires_at, true)}</>}
      </p>

      {current.error && <p className="error">Failed: {current.error}</p>}
      {manualText && (
        <div className="manual">
          <p>Approved. There is no API for this action, so copy the text and paste it yourself:</p>
          <button type="button" className="ghost" onClick={() => navigator.clipboard?.writeText(manualText)}>
            Copy text
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}

      {pending && (
        <div className="row">
          {editing ? (
            <>
              <button type="button" disabled={busy || !draftBody.trim()} onClick={() => run(() => api.editApproval(current.id, { body: draftBody, subject: current.subject === null ? null : draftSubject }))}>
                Save as new preview
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={() => setEditing(false)}>
                Cancel
              </button>
            </>
          ) : (
            <>
              <button type="button" disabled={busy} onClick={() => run(() => api.approve(current))}>
                Approve &amp; send exactly this
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={() => setEditing(true)}>
                Edit
              </button>
              <button type="button" className="danger" disabled={busy} onClick={() => run(() => api.reject(current.id))}>
                Reject
              </button>
            </>
          )}
        </div>
      )}
    </article>
  );
}
