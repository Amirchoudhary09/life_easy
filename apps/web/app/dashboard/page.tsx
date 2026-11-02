"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type User = { id: string; email: string; display_name: string | null; email_verified: boolean };
type Profile = { headline?: string | null; location?: string | null; experience_years?: number | null; skills?: string[]; preferences?: Record<string, unknown> };
type Job = { id: string; company: string; title: string; location: string | null; apply_url: string; source: string; match?: { score: number; matched_skills: string[]; location_match: boolean }; saved_status: string | null };

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile>({});
  const [headline, setHeadline] = useState("");
  const [location, setLocation] = useState("");
  const [experience, setExperience] = useState("0");
  const [skills, setSkills] = useState("");
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("software engineer");
  const [jobLocations, setJobLocations] = useState("India");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobMessage, setJobMessage] = useState("");
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(true);

  function token() { return sessionStorage.getItem("life_easy_token"); }

  useEffect(() => {
    const accessToken = token();
    if (!accessToken) { router.replace("/login"); return; }
    fetch(`${API}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then(async r => { if (!r.ok) throw new Error("Session expired"); return r.json(); })
      .then(async data => {
        setUser(data.user);
        const p = await fetch(`${API}/api/v1/profile`, { headers: { Authorization: `Bearer ${accessToken}` } });
        if (p.ok) {
          const result = await p.json();
          if (result.profile) {
            setProfile(result.profile);
            setHeadline(result.profile.headline || "");
            setLocation(result.profile.location || "");
            setExperience(String(result.profile.experience_years ?? 0));
            setSkills((result.profile.skills || []).join(", "));
          }
        }
      })
      .catch(() => { sessionStorage.removeItem("life_easy_token"); router.replace("/login"); })
      .finally(() => setBusy(false));
  }, [router]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const accessToken = token();
    if (!accessToken) return router.replace("/login");
    setMessage("");
    const response = await fetch(`${API}/api/v1/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ headline: headline || null, location: location || null, experience_years: Number(experience), skills: skills.split(",").map(s => s.trim()).filter(Boolean), preferences: profile.preferences || {} }),
    });
    const data = await response.json();
    setMessage(response.ok ? "Career profile saved." : data.detail || "Could not save profile.");
  }

  async function searchJobs(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const accessToken = token();
    if (!accessToken) return router.replace("/login");
    setSearching(true);
    setJobMessage("");
    setJobs([]);
    try {
      const response = await fetch(`${API}/api/v1/jobs/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ query, locations: jobLocations.split(",").map(s => s.trim()).filter(Boolean), limit: 25 }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Job search failed.");
      setJobs(data.jobs || []);
      setJobMessage(data.message || `Found ${data.count || 0} indexed jobs.`);
    } catch (err) {
      setJobMessage(err instanceof Error ? err.message : "Job search failed.");
    } finally {
      setSearching(false);
    }
  }

  async function saveJob(jobId: string) {
    const accessToken = token();
    if (!accessToken) return router.replace("/login");
    const response = await fetch(`${API}/api/v1/jobs/${jobId}/save`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}` } });
    if (response.ok) setJobs(current => current.map(job => job.id === jobId ? { ...job, saved_status: "saved" } : job));
  }

  function logout() {
    sessionStorage.removeItem("life_easy_token");
    router.replace("/login");
  }

  if (busy || !user) return <main className="dashboard-shell"><p>Loading your workspace...</p></main>;

  return <main className="dashboard-shell">
    <nav className="nav"><Link className="brand" href="/">life<span>easy</span></Link><div className="user-menu"><span>{user.display_name || user.email}</span><button onClick={logout}>Log out</button></div></nav>
    <section className="dash-welcome"><p className="eyebrow">YOUR CAREER WORKSPACE</p><h1>Good to have you here, {user.display_name || "there"}.</h1><p>Complete your profile, then search the job records indexed for Life Easy. Live source connectors are the next integration milestone.</p></section>
    <section className="dash-panel job-search-panel">
      <div className="panel-heading"><div><p className="eyebrow">CORE MODULE</p><h2>Find opportunities</h2></div><span className="status">Job discovery</span></div>
      <form className="job-search-form" onSubmit={searchJobs}>
        <label>Role or skills<input value={query} onChange={e => setQuery(e.target.value)} minLength={2} placeholder="e.g. Backend Engineer, Python"/></label>
        <label>Locations (comma separated)<input value={jobLocations} onChange={e => setJobLocations(e.target.value)} placeholder="India, Noida, Remote"/></label>
        <button className="primary" disabled={searching}>{searching ? "Searching..." : "Search indexed jobs"} <span>→</span></button>
      </form>
      {jobMessage && <p className="form-message" role="status">{jobMessage}</p>}
      <div className="job-results">
        {jobs.map(job => <article className="job-card" key={job.id}>
          <div><p className="job-company">{job.company}</p><h3>{job.title}</h3><p className="job-meta">{job.location || "Location not listed"} · {job.source}</p></div>
          <div className="job-actions"><span className="job-score">{job.match?.score ?? 0}% match</span><button type="button" onClick={() => saveJob(job.id)} disabled={job.saved_status === "saved"}>{job.saved_status === "saved" ? "Saved" : "Save job"}</button><a href={job.apply_url} target="_blank" rel="noreferrer">View role ↗</a></div>
        </article>)}
      </div>
    </section>
    <div className="dash-grid">
      <section className="dash-panel profile-panel">
        <div className="panel-heading"><div><p className="eyebrow">SETUP 01</p><h2>Career profile</h2></div><span className="status">Your details</span></div>
        <form className="profile-form" onSubmit={saveProfile}>
          <label>Professional headline<input value={headline} onChange={e => setHeadline(e.target.value)} placeholder="e.g. Software Developer | C++ | Python"/></label>
          <label>Preferred location<input value={location} onChange={e => setLocation(e.target.value)} placeholder="e.g. Noida, Bengaluru, Remote"/></label>
          <label>Years of experience<input type="number" min="0" max="60" step="0.5" value={experience} onChange={e => setExperience(e.target.value)}/></label>
          <label>Skills (comma separated)<textarea value={skills} onChange={e => setSkills(e.target.value)} placeholder="C++, Python, SQL, FastAPI"/></label>
          <button className="primary" type="submit">Save career profile <span>→</span></button>
          {message && <p className="form-message" role="status">{message}</p>}
        </form>
      </section>
      <section className="dash-panel">
        <p className="eyebrow">NEXT MODULES</p><h2>Your career toolkit</h2>
        <div className="module-row"><b>Resume upload & ATS</b><span>Storage integration pending</span></div>
        <div className="module-row"><b>Recruiter research</b><span>Public source adapters pending</span></div>
        <div className="module-row"><b>Gmail outreach</b><span>OAuth integration pending</span></div>
        <div className="module-row"><b>LinkedIn career tools</b><span>Authorized integration pending</span></div>
        <p className="auth-foot">No fake job listings are shown. Search currently reads jobs already indexed in the database.</p>
      </section>
    </div>
  </main>;
}
