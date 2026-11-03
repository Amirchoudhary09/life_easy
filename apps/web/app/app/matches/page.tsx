"use client";

import { useState } from "react";

import { Empty, Notice, PageHead, useLoad } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Match, MatchStatus, TailorResult } from "@/lib/types";

const FILTERS: { value: MatchStatus; label: string }[] = [
  { value: "suggested", label: "Suggested" },
  { value: "saved", label: "Saved" },
  { value: "applied", label: "Applied" },
  { value: "skipped", label: "Skipped" },
];

export default function MatchesPage() {
  const [filter, setFilter] = useState<MatchStatus>("suggested");
  const { data, setData, error, setError, loading, reload } = useLoad(() => api.matches(filter), [filter]);
  const [notice, setNotice] = useState<string | null>(null);
  const [tailored, setTailored] = useState<Record<string, TailorResult>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  async function act(match: Match, status: MatchStatus) {
    setBusyId(match.job.id);
    try {
      await api.setMatch(match.job.id, status);
      setData((rows) => (rows ?? []).filter((m) => m.job.id !== match.job.id));
      setNotice(status === "applied" ? `Added ${match.job.title} at ${match.job.company} to your tracker. I'll remind you to follow up in 7 days.` : null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function tailor(match: Match) {
    setBusyId(match.job.id);
    try {
      const res = await api.tailor(match.job.id);
      setTailored((t) => ({ ...t, [match.job.id]: res }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function refresh() {
    try {
      await api.refreshMatches();
      setNotice("Recomputing your matches. This takes a few seconds.");
      setTimeout(() => void reload(), 3000);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section>
      <PageHead eyebrow="JOB MATCHES" title="Roles that fit you">
        <button type="button" className="ghost" onClick={() => void refresh()}>
          Refresh matches
        </button>
      </PageHead>
      <div className="filters">
        {FILTERS.map((f) => (
          <button key={f.value} type="button" className={filter === f.value ? "chip active" : "chip"} onClick={() => setFilter(f.value)}>
            {f.label}
          </button>
        ))}
      </div>
      <Notice kind="success">{notice}</Notice>
      <Notice kind="error">{error}</Notice>
      {loading && <p className="loading">Loading…</p>}
      {!loading && data?.length === 0 && (
        <Empty>
          No {filter} matches yet. Upload a resume and set your preferences in Settings, then press <b>Refresh matches</b>.
        </Empty>
      )}
      <div className="list">
        {data?.map((match) => {
          const e = match.explanation ?? {};
          const t = tailored[match.job.id];
          return (
            <article className="item" key={match.job.id}>
              <div className="item-head">
                <div>
                  <h3>
                    {match.job.title} <span className="muted">at {match.job.company}</span>
                  </h3>
                  <p className="muted small">
                    {match.job.location || "Location n/a"}
                    {match.job.remote ? " · remote" : ""}
                    {match.job.employment_type ? ` · ${match.job.employment_type}` : ""}
                    {match.job.salary_text ? ` · ${match.job.salary_text}` : ""} · posted {fmtDate(match.job.posted_at)} · via {match.job.source}
                  </p>
                </div>
                <span className={`score ${match.score >= 70 ? "high" : match.score >= 45 ? "mid" : "low"}`}>{Math.round(match.score)}%</span>
              </div>
              {e.summary && <p>{e.summary}</p>}
              <div className="two-col">
                {e.strengths && e.strengths.length > 0 && (
                  <ul className="good">
                    {e.strengths.slice(0, 5).map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                )}
                {e.gaps && e.gaps.length > 0 && (
                  <ul className="gap">
                    {e.gaps.slice(0, 5).map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="row">
                <a className="ghost-link" href={match.job.apply_url} target="_blank" rel="noopener noreferrer">
                  Open posting ↗
                </a>
                {match.status !== "saved" && (
                  <button type="button" className="ghost" disabled={busyId === match.job.id} onClick={() => void act(match, "saved")}>
                    Save
                  </button>
                )}
                {match.status !== "applied" && (
                  <button type="button" className="ghost" disabled={busyId === match.job.id} onClick={() => void act(match, "applied")}>
                    I applied
                  </button>
                )}
                <button type="button" className="ghost" disabled={busyId === match.job.id} onClick={() => void tailor(match)}>
                  Tailor resume
                </button>
                {match.status !== "skipped" && (
                  <button type="button" className="ghost" disabled={busyId === match.job.id} onClick={() => void act(match, "skipped")}>
                    Skip
                  </button>
                )}
              </div>
              {t && (
                <details className="tailored" open>
                  <summary>
                    Tailored resume · ATS keyword score {t.ats.score ?? "?"}/100
                    {t.ats.missing_keywords && t.ats.missing_keywords.length > 0 && <> · missing: {t.ats.missing_keywords.join(", ")}</>}
                  </summary>
                  <pre>{t.markdown}</pre>
                  <p className="hint">Saved under Resumes as “{t.resume.filename}”. Check it before sending: it only rewords what is in your original.</p>
                </details>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
