"use client";

import { useRef, useState } from "react";

import { Empty, Notice, PageHead, useLoad } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtBytes, fmtDate, saveBlob } from "@/lib/format";
import type { Resume } from "@/lib/types";

export default function ResumesPage() {
  const { data, error, setError, loading, reload } = useLoad(() => api.resumes());
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function upload(file: File | undefined) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError("The file is larger than 5 MB.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.uploadResume(file);
      setNotice("Uploaded. I'm reading it now; your profile and matches update in a moment.");
      await reload();
      setTimeout(() => void reload(), 4000);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function run(fn: () => Promise<unknown>) {
    try {
      await fn();
      await reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const originals = (data ?? []).filter((r) => !r.tailored_for_job_id);
  const tailored = (data ?? []).filter((r) => r.tailored_for_job_id);

  const row = (r: Resume) => {
    const parsed = r.parsed as { headline?: string; skills?: string[]; ats?: { score?: number } };
    return (
      <article className="item" key={r.id}>
        <div className="item-head">
          <div>
            <h3>
              {r.filename} {r.is_primary && <span className="badge badge-executed">primary</span>}
            </h3>
            <p className="muted small">
              {fmtBytes(r.size_bytes)} · uploaded {fmtDate(r.created_at)} · {r.has_text ? "read" : "reading…"}
              {parsed.ats?.score !== undefined ? ` · ATS score ${parsed.ats.score}/100` : ""}
            </p>
            {parsed.headline && <p>{parsed.headline}</p>}
            {parsed.skills && parsed.skills.length > 0 && <p className="muted small">Skills found: {parsed.skills.slice(0, 20).join(", ")}</p>}
          </div>
        </div>
        <div className="row">
          <button type="button" className="ghost" onClick={() => void run(async () => saveBlob(await api.downloadResume(r.id), r.filename))}>
            Download
          </button>
          {!r.is_primary && !r.tailored_for_job_id && (
            <button type="button" className="ghost" onClick={() => void run(() => api.setPrimaryResume(r.id))}>
              Make primary
            </button>
          )}
          <button
            type="button"
            className="danger"
            onClick={() => {
              if (window.confirm(`Delete ${r.filename}?`)) void run(() => api.deleteResume(r.id));
            }}
          >
            Delete
          </button>
        </div>
      </article>
    );
  };

  return (
    <section>
      <PageHead eyebrow="RESUMES" title="Your resumes">
        <label className={`button ${busy ? "disabled" : ""}`}>
          {busy ? "Uploading…" : "Upload resume"}
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md" hidden disabled={busy} onChange={(e) => void upload(e.target.files?.[0])} />
        </label>
      </PageHead>
      <p className="muted">PDF, DOCX, TXT or Markdown, up to 5 MB. Files are stored privately; only you can download them.</p>
      <Notice kind="success">{notice}</Notice>
      <Notice kind="error">{error}</Notice>
      {loading && <p className="loading">Loading…</p>}
      {!loading && originals.length === 0 && <Empty>No resume yet. Upload one so I can match jobs to you.</Empty>}
      <div className="list">{originals.map(row)}</div>
      {tailored.length > 0 && (
        <>
          <h2 className="section-title">Tailored versions</h2>
          <div className="list">{tailored.map(row)}</div>
        </>
      )}
    </section>
  );
}
