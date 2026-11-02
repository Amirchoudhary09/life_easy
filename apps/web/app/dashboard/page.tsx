"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type User = { id: string; email: string; display_name: string | null; email_verified: boolean };
type Profile = { headline?: string | null; location?: string | null; experience_years?: number | null; skills?: string[]; preferences?: Record<string, unknown> };

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile>({});
  const [headline, setHeadline] = useState("");
  const [location, setLocation] = useState("");
  const [experience, setExperience] = useState("0");
  const [skills, setSkills] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    const token = sessionStorage.getItem("life_easy_token");
    if (!token) { router.replace("/login"); return; }
    fetch(`${API}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async r => { if (!r.ok) throw new Error("Session expired"); return r.json(); })
      .then(async data => {
        setUser(data.user);
        const p = await fetch(`${API}/api/v1/profile`, { headers: { Authorization: `Bearer ${token}` } });
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

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = sessionStorage.getItem("life_easy_token");
    if (!token) return router.replace("/login");
    setMessage("");
    const response = await fetch(`${API}/api/v1/profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ headline: headline || null, location: location || null, experience_years: Number(experience), skills: skills.split(",").map(s => s.trim()).filter(Boolean), preferences: profile.preferences || {} }),
    });
    const data = await response.json();
    setMessage(response.ok ? "Career profile saved." : data.detail || "Could not save profile.");
  }

  function logout() {
    sessionStorage.removeItem("life_easy_token");
    router.replace("/login");
  }

  if (busy || !user) return <main className="dashboard-shell"><p>Loading your workspace...</p></main>;

  return <main className="dashboard-shell">
    <nav className="nav"><Link className="brand" href="/">life<span>easy</span></Link><div className="user-menu"><span>{user.display_name || user.email}</span><button onClick={logout}>Log out</button></div></nav>
    <section className="dash-welcome"><p className="eyebrow">YOUR CAREER WORKSPACE</p><h1>Good to have you here, {user.display_name || "there"}.</h1><p>Start by completing your career profile. Job discovery and resume matching will use these preferences.</p></section>
    <div className="dash-grid">
      <section className="dash-panel profile-panel">
        <div className="panel-heading"><div><p className="eyebrow">STEP 01</p><h2>Career profile</h2></div><span className="status">Setup</span></div>
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
        <p className="eyebrow">NEXT MODULES</p><h2>Your job search toolkit</h2>
        <div className="module-row"><b>Job discovery</b><span>Source adapters pending</span></div>
        <div className="module-row"><b>Resume upload</b><span>Private storage pending</span></div>
        <div className="module-row"><b>Recruiter research</b><span>Source integrations pending</span></div>
        <div className="module-row"><b>Email & LinkedIn</b><span>Connect accounts later</span></div>
        <p className="auth-foot">We will activate these modules as their integrations are completed. No fake job results are shown.</p>
      </section>
    </div>
  </main>;
}
