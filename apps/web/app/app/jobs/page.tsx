"use client";

import { useState, type FormEvent } from "react";

import { Empty, Notice, PageHead } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Job, JobSummary, Page } from "@/lib/types";

const PAGE_SIZE = 20;

export default function JobsPage() {
  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("");
  const [remote, setRemote] = useState<"" | "yes" | "no">("");
  const [page, setPage] = useState<Page<JobSummary> | null>(null);
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<Job | null>(null);
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function search(nextOffset = 0) {
    setBusy(true);
    setError(null);
    try {
      setPage(await api.jobs({ query, location, remote: remote === "" ? null : remote === "yes", limit: PAGE_SIZE, offset: nextOffset }));
      setOffset(nextOffset);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void search(0);
  }

  async function save(job: JobSummary) {
    try {
      await api.setMatch(job.id, "saved");
      setSaved((s) => new Set(s).add(job.id));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function ingest() {
    try {
      await api.ingest();
      setNotice("Fetching new jobs from your configured sources. Search again in a minute.");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <section>
      <PageHead eyebrow="JOB SEARCH" title="Search all jobs">
        <button type="button" className="ghost" onClick={() => void ingest()}>
          Fetch new jobs
        </button>
      </PageHead>
      <form className="search" onSubmit={onSubmit}>
        <input placeholder="Title, skill or company" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={200} />
        <input placeholder="Location" value={location} onChange={(e) => setLocation(e.target.value)} maxLength={120} />
        <select value={remote} onChange={(e) => setRemote(e.target.value as typeof remote)} aria-label="Remote">
          <option value="">Remote or not</option>
          <option value="yes">Remote only</option>
          <option value="no">On-site only</option>
        </select>
        <button type="submit" disabled={busy}>
          Search
        </button>
      </form>
      <Notice kind="success">{notice}</Notice>
      <Notice kind="error">{error}</Notice>
      {page && page.items.length === 0 && <Empty>No jobs found. Try fewer words, or press “Fetch new jobs”.</Empty>}
      {page && page.items.length > 0 && (
        <p className="muted small">
          {page.total} jobs · showing {offset + 1}–{offset + page.items.length}
        </p>
      )}
      <div className="list">
        {page?.items.map((job) => (
          <article className="item" key={job.id}>
            <div className="item-head">
              <div>
                <h3>
                  {job.title} <span className="muted">at {job.company}</span>
                </h3>
                <p className="muted small">
                  {job.location || "Location n/a"}
                  {job.remote ? " · remote" : ""}
                  {job.employment_type ? ` · ${job.employment_type}` : ""}
                  {job.salary_text ? ` · ${job.salary_text}` : ""} · posted {fmtDate(job.posted_at)} · via {job.source}
                </p>
              </div>
            </div>
            <div className="row">
              <a className="ghost-link" href={job.apply_url} target="_blank" rel="noopener noreferrer">
                Open posting ↗
              </a>
              <button type="button" className="ghost" onClick={() => void api.job(job.id).then(setOpen).catch((e) => setError(errorMessage(e)))}>
                Details
              </button>
              <button type="button" className="ghost" disabled={saved.has(job.id)} onClick={() => void save(job)}>
                {saved.has(job.id) ? "Saved" : "Save"}
              </button>
            </div>
            {open?.id === job.id && <pre className="description">{open.description || "No description provided by the source."}</pre>}
          </article>
        ))}
      </div>
      {page && page.total > PAGE_SIZE && (
        <div className="row pager">
          <button type="button" className="ghost" disabled={offset === 0 || busy} onClick={() => void search(Math.max(0, offset - PAGE_SIZE))}>
            ← Previous
          </button>
          <button type="button" className="ghost" disabled={offset + PAGE_SIZE >= page.total || busy} onClick={() => void search(offset + PAGE_SIZE)}>
            Next →
          </button>
        </div>
      )}
    </section>
  );
}
