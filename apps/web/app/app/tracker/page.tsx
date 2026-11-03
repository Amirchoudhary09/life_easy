"use client";

import { useState, type FormEvent } from "react";

import { Empty, Notice, PageHead, useLoad } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { APPLICATION_STATUSES, type Application, type ApplicationStatus } from "@/lib/types";

const BOARD: ApplicationStatus[] = ["planned", "applied", "screening", "interview", "offer"];
const CLOSED: ApplicationStatus[] = ["accepted", "rejected", "withdrawn"];

export default function TrackerPage() {
  const apps = useLoad(() => api.applications());
  const stats = useLoad(() => api.stats());
  const interviews = useLoad(() => api.interviews());
  const followUps = useLoad(() => api.followUps());
  const [error, setError] = useState<string | null>(null);
  const [showClosed, setShowClosed] = useState(false);
  const [form, setForm] = useState({ company: "", title: "", status: "applied" as ApplicationStatus, source_url: "" });
  const [interviewFor, setInterviewFor] = useState<string | null>(null);
  const [interviewForm, setInterviewForm] = useState({ when: "", kind: "video", location: "" });

  const byId = new Map((apps.data?.items ?? []).map((a) => [a.id, a]));
  const reloadAll = () => Promise.all([apps.reload(), stats.reload(), interviews.reload(), followUps.reload()]);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.addApplication({ ...form, source_url: form.source_url || undefined });
      setForm({ company: "", title: "", status: "applied", source_url: "" });
      await reloadAll();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function move(app: Application, status: ApplicationStatus) {
    try {
      await api.updateApplication(app.id, { status });
      await reloadAll();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function addInterview(e: FormEvent) {
    e.preventDefault();
    if (!interviewFor || !interviewForm.when) return;
    try {
      await api.addInterview(interviewFor, { scheduled_at: new Date(interviewForm.when).toISOString(), kind: interviewForm.kind, location: interviewForm.location || undefined });
      setInterviewFor(null);
      setInterviewForm({ when: "", kind: "video", location: "" });
      await reloadAll();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const columns = showClosed ? [...BOARD, ...CLOSED] : BOARD;

  return (
    <section>
      <PageHead eyebrow="APPLICATION TRACKER" title="Where every application stands">
        <label className="inline">
          <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} /> Show closed
        </label>
      </PageHead>
      {stats.data && (
        <div className="stats">
          <div>
            <b>{stats.data.applied_last_7_days}</b>
            <span>applied this week</span>
          </div>
          <div>
            <b>{stats.data.interviews_upcoming}</b>
            <span>upcoming interviews</span>
          </div>
          <div>
            <b>{stats.data.follow_ups_due}</b>
            <span>follow-ups due</span>
          </div>
          <div>
            <b>{Object.values(stats.data.by_status).reduce((a, b) => a + b, 0)}</b>
            <span>tracked in total</span>
          </div>
        </div>
      )}
      <Notice kind="error">{error || apps.error}</Notice>

      <form className="search" onSubmit={add}>
        <input required placeholder="Company" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} maxLength={200} />
        <input required placeholder="Role" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} maxLength={300} />
        <input placeholder="Posting URL (optional)" value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} maxLength={1000} />
        <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as ApplicationStatus })} aria-label="Status">
          {APPLICATION_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button type="submit">Add application</button>
      </form>

      {apps.data && apps.data.items.length === 0 && <Empty>Nothing tracked yet. Mark a match as “I applied” or add one above.</Empty>}

      <div className="board">
        {columns.map((status) => {
          const items = (apps.data?.items ?? []).filter((a) => a.status === status);
          return (
            <div className="column" key={status}>
              <h3>
                {status} <span className="muted">{items.length}</span>
              </h3>
              {items.map((app) => (
                <article className="mini" key={app.id}>
                  <b>{app.title}</b>
                  <span className="muted">{app.company}</span>
                  <span className="muted small">
                    {app.applied_at ? `applied ${fmtDate(app.applied_at)}` : `added ${fmtDate(app.created_at)}`}
                    {app.next_follow_up_at ? ` · follow up ${fmtDate(app.next_follow_up_at)}` : ""}
                  </span>
                  <select value={app.status} onChange={(e) => void move(app, e.target.value as ApplicationStatus)} aria-label={`Status of ${app.title}`}>
                    {APPLICATION_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                  <button type="button" className="link" onClick={() => setInterviewFor(app.id)}>
                    + interview
                  </button>
                  {app.source_url && (
                    <a className="small" href={app.source_url} target="_blank" rel="noopener noreferrer">
                      posting ↗
                    </a>
                  )}
                </article>
              ))}
            </div>
          );
        })}
      </div>

      {interviewFor && (
        <form className="panel" onSubmit={addInterview}>
          <h3>Add interview · {byId.get(interviewFor)?.title} at {byId.get(interviewFor)?.company}</h3>
          <div className="search">
            <input type="datetime-local" required value={interviewForm.when} onChange={(e) => setInterviewForm({ ...interviewForm, when: e.target.value })} />
            <select value={interviewForm.kind} onChange={(e) => setInterviewForm({ ...interviewForm, kind: e.target.value })} aria-label="Kind">
              <option value="phone">Phone</option>
              <option value="video">Video</option>
              <option value="onsite">On-site</option>
              <option value="test">Assessment</option>
            </select>
            <input placeholder="Link or address" value={interviewForm.location} onChange={(e) => setInterviewForm({ ...interviewForm, location: e.target.value })} />
            <button type="submit">Save</button>
            <button type="button" className="ghost" onClick={() => setInterviewFor(null)}>
              Cancel
            </button>
          </div>
          <p className="hint">You&apos;ll get a prep pack the day before.</p>
        </form>
      )}

      <div className="two-col">
        <div className="panel">
          <h3>Upcoming interviews</h3>
          {(interviews.data ?? []).length === 0 && <p className="muted">None scheduled.</p>}
          <ul className="plain">
            {interviews.data?.map((i) => (
              <li key={i.id}>
                <b>{fmtDate(i.scheduled_at, true)}</b> · {i.kind} · {byId.get(i.application_id)?.title ?? "?"} at {byId.get(i.application_id)?.company ?? "?"}
                {i.location ? ` · ${i.location}` : ""}
                {i.prep_sent_at ? " · prep sent" : ""}
              </li>
            ))}
          </ul>
        </div>
        <div className="panel">
          <h3>Follow-ups</h3>
          {(followUps.data ?? []).length === 0 && <p className="muted">Nothing due. Follow-ups are scheduled 7 days after you apply.</p>}
          <ul className="plain">
            {followUps.data?.map((f) => (
              <li key={f.id}>
                <b>{fmtDate(f.due_at)}</b> · {byId.get(f.application_id)?.company ?? "?"} · {f.status}
                {f.approval_id ? " · draft waiting in Approvals" : ""}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
