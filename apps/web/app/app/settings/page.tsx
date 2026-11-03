"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Notice, PageHead, useLoad } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, saveBlob, splitList } from "@/lib/format";
import type { LinkCode, Preferences, Profile } from "@/lib/types";

const IMAP_PRESETS: Record<string, { imap_host: string; imap_port: number; smtp_host: string; smtp_port: number }> = {
  Gmail: { imap_host: "imap.gmail.com", imap_port: 993, smtp_host: "smtp.gmail.com", smtp_port: 587 },
  Outlook: { imap_host: "outlook.office365.com", imap_port: 993, smtp_host: "smtp.office365.com", smtp_port: 587 },
  Yahoo: { imap_host: "imap.mail.yahoo.com", imap_port: 993, smtp_host: "smtp.mail.yahoo.com", smtp_port: 465 },
  Zoho: { imap_host: "imap.zoho.in", imap_port: 993, smtp_host: "smtp.zoho.in", smtp_port: 465 },
  iCloud: { imap_host: "imap.mail.me.com", imap_port: 993, smtp_host: "smtp.mail.me.com", smtp_port: 587 },
};

function ProfileForm({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const { user, reloadUser } = useAuth();
  const prefs = profile.preferences ?? {};
  const [f, setF] = useState({
    display_name: user?.display_name ?? "",
    headline: profile.headline ?? "",
    location: profile.location ?? "",
    experience_years: profile.experience_years?.toString() ?? "",
    skills: (profile.skills ?? []).join(", "),
    titles: (prefs.titles ?? []).join(", "),
    locations: (prefs.locations ?? []).join(", "),
    remote: (prefs.remote ?? "any") as Preferences["remote"],
    employment_types: (prefs.employment_types ?? ["full-time"]).join(", "),
    salary_min: prefs.salary_min?.toString() ?? "",
    currency: prefs.currency ?? "INR",
    exclude_companies: (prefs.exclude_companies ?? []).join(", "),
    digest_hour_local: String(prefs.digest_hour_local ?? 9),
    timezone: profile.timezone ?? "Asia/Kolkata",
    digest_enabled: profile.digest_enabled,
  });
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const saved = await api.updateProfile({
        display_name: f.display_name || undefined,
        headline: f.headline || null,
        location: f.location || null,
        experience_years: f.experience_years ? Number(f.experience_years) : null,
        skills: splitList(f.skills),
        timezone: f.timezone,
        digest_enabled: f.digest_enabled,
        preferences: {
          titles: splitList(f.titles),
          locations: splitList(f.locations),
          remote: f.remote,
          employment_types: splitList(f.employment_types),
          salary_min: f.salary_min ? Number(f.salary_min) : null,
          currency: f.currency || "INR",
          exclude_companies: splitList(f.exclude_companies),
          digest_hour_local: Number(f.digest_hour_local) || 9,
        },
      });
      await reloadUser();
      onSaved(saved);
      setMsg({ kind: "success", text: "Saved. Your matches will refresh with the new preferences." });
      void api.refreshMatches().catch(() => undefined);
    } catch (err) {
      setMsg({ kind: "error", text: errorMessage(err) });
    }
  }

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  return (
    <form className="panel form-grid" onSubmit={save}>
      <h2>Profile &amp; job preferences</h2>
      <label>
        Name
        <input value={f.display_name} onChange={set("display_name")} maxLength={120} />
      </label>
      <label>
        Headline
        <input value={f.headline} onChange={set("headline")} placeholder="Backend developer" maxLength={200} />
      </label>
      <label>
        Current location
        <input value={f.location} onChange={set("location")} placeholder="Bengaluru" maxLength={120} />
      </label>
      <label>
        Years of experience
        <input type="number" min={0} max={60} step={0.5} value={f.experience_years} onChange={set("experience_years")} />
      </label>
      <label className="wide">
        Skills (comma separated)
        <input value={f.skills} onChange={set("skills")} placeholder="Python, FastAPI, PostgreSQL" />
      </label>
      <label className="wide">
        Roles you want (comma separated)
        <input value={f.titles} onChange={set("titles")} placeholder="Backend engineer, SDE" />
      </label>
      <label>
        Preferred locations
        <input value={f.locations} onChange={set("locations")} placeholder="Bengaluru, Pune" />
      </label>
      <label>
        Remote
        <select value={f.remote} onChange={set("remote")}>
          <option value="any">Any</option>
          <option value="remote">Remote only</option>
          <option value="hybrid">Hybrid</option>
          <option value="onsite">On-site</option>
        </select>
      </label>
      <label>
        Employment types
        <input value={f.employment_types} onChange={set("employment_types")} placeholder="full-time, internship" />
      </label>
      <label>
        Minimum salary
        <span className="row">
          <input type="number" min={0} value={f.salary_min} onChange={set("salary_min")} />
          <input className="short" value={f.currency} onChange={set("currency")} maxLength={3} aria-label="Currency" />
        </span>
      </label>
      <label className="wide">
        Never show jobs from (comma separated)
        <input value={f.exclude_companies} onChange={set("exclude_companies")} />
      </label>
      <label>
        Time zone
        <input value={f.timezone} onChange={set("timezone")} placeholder="Asia/Kolkata" maxLength={64} />
      </label>
      <label>
        Daily digest hour (local)
        <input type="number" min={0} max={23} value={f.digest_hour_local} onChange={set("digest_hour_local")} />
      </label>
      <label className="inline wide">
        <input type="checkbox" checked={f.digest_enabled} onChange={(e) => setF({ ...f, digest_enabled: e.target.checked })} /> Send me a daily job digest and weekly report
      </label>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <div className="wide">
        <button type="submit">Save profile</button>
      </div>
    </form>
  );
}

function EmailConnections() {
  const conns = useLoad(() => api.connections());
  const [error, setError] = useState<string | null>(null);
  const [imap, setImap] = useState({ account_email: "", username: "", password: "", ...IMAP_PRESETS.Gmail });

  async function oauth(provider: "google" | "microsoft" | "linkedin") {
    setError(null);
    try {
      const { url } = await api.oauthStart(provider);
      window.location.href = url;
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function addImap(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.addImap({ ...imap, username: imap.username || undefined });
      setImap({ account_email: "", username: "", password: "", ...IMAP_PRESETS.Gmail });
      await conns.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="panel">
      <h2>Email &amp; LinkedIn</h2>
      <p className="muted">Life Easy sends from your own mailbox, only after you approve each message. You can disconnect at any time.</p>
      <ul className="plain">
        {conns.data?.map((c) => (
          <li key={c.id} className="row spread">
            <span>
              <b>{c.provider}</b> · {c.account_email} · connected {fmtDate(c.created_at)}
              {c.last_error && <span className="error"> · {c.last_error}</span>}
            </span>
            <button type="button" className="danger" onClick={() => void api.removeConnection(c.id).then(conns.reload).catch((err) => setError(errorMessage(err)))}>
              Disconnect
            </button>
          </li>
        ))}
        {conns.data?.length === 0 && <li className="muted">No accounts connected yet.</li>}
      </ul>
      <div className="row">
        <button type="button" className="ghost" onClick={() => void oauth("google")}>
          Connect Gmail
        </button>
        <button type="button" className="ghost" onClick={() => void oauth("microsoft")}>
          Connect Outlook / Microsoft 365
        </button>
        <button type="button" className="ghost" onClick={() => void oauth("linkedin")}>
          Connect LinkedIn
        </button>
      </div>
      <details>
        <summary>Any other mailbox (IMAP / SMTP with an app password)</summary>
        <form className="form-grid" onSubmit={addImap}>
          <label>
            Provider preset
            <select
              onChange={(e) => {
                const preset = IMAP_PRESETS[e.target.value];
                if (preset) setImap({ ...imap, ...preset });
              }}
            >
              {Object.keys(IMAP_PRESETS).map((k) => (
                <option key={k}>{k}</option>
              ))}
              <option value="custom">Custom</option>
            </select>
          </label>
          <label>
            Email address
            <input type="email" required value={imap.account_email} onChange={(e) => setImap({ ...imap, account_email: e.target.value })} />
          </label>
          <label>
            Username (if different)
            <input value={imap.username} onChange={(e) => setImap({ ...imap, username: e.target.value })} />
          </label>
          <label>
            App password
            <input type="password" required value={imap.password} onChange={(e) => setImap({ ...imap, password: e.target.value })} autoComplete="new-password" />
          </label>
          <label>
            IMAP host / port
            <span className="row">
              <input required value={imap.imap_host} onChange={(e) => setImap({ ...imap, imap_host: e.target.value })} />
              <input className="short" type="number" value={imap.imap_port} onChange={(e) => setImap({ ...imap, imap_port: Number(e.target.value) })} />
            </span>
          </label>
          <label>
            SMTP host / port
            <span className="row">
              <input required value={imap.smtp_host} onChange={(e) => setImap({ ...imap, smtp_host: e.target.value })} />
              <input className="short" type="number" value={imap.smtp_port} onChange={(e) => setImap({ ...imap, smtp_port: Number(e.target.value) })} />
            </span>
          </label>
          <p className="hint wide">Use an app password, not your normal password. It is checked by logging in once, then stored encrypted.</p>
          <div className="wide">
            <button type="submit">Connect mailbox</button>
          </div>
        </form>
      </details>
      <Notice kind="error">{error || conns.error}</Notice>
    </div>
  );
}

function Messaging() {
  const channels = useLoad(() => api.channels());
  const [code, setCode] = useState<LinkCode | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="panel">
      <h2>WhatsApp &amp; Telegram</h2>
      <p className="muted">Chat with Life Easy from your phone. Generate a code here, then send it from the app you want to link.</p>
      <ul className="plain">
        {channels.data?.map((c) => (
          <li key={c.id} className="row spread">
            <span>
              <b>{c.provider}</b> · {c.display_name || "linked chat"} {c.external_id_hint} · since {fmtDate(c.verified_at)}
            </span>
            <button type="button" className="danger" onClick={() => void api.unlinkChannel(c.id).then(channels.reload).catch((err) => setError(errorMessage(err)))}>
              Unlink
            </button>
          </li>
        ))}
        {channels.data?.length === 0 && <li className="muted">No chat apps linked.</li>}
      </ul>
      <div className="row">
        <button type="button" className="ghost" onClick={() => void api.linkCode().then(setCode).catch((err) => setError(errorMessage(err)))}>
          Get a link code
        </button>
        <button type="button" className="ghost" onClick={() => void channels.reload()}>
          I sent it — refresh
        </button>
      </div>
      {code && (
        <div className="code-box">
          <code>LINK {code.code}</code>
          <p className="small">{code.instructions}</p>
          {!code.channels.whatsapp && !code.channels.telegram && <p className="error small">No chat channel is configured on the server yet.</p>}
        </div>
      )}
      <Notice kind="error">{error || channels.error}</Notice>
    </div>
  );
}

function DataControls() {
  const router = useRouter();
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="panel">
      <h2>Your data</h2>
      <div className="row">
        <button
          type="button"
          className="ghost"
          onClick={() =>
            void api
              .exportData()
              .then((data) => saveBlob(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }), "life-easy-export.json"))
              .catch((err) => setError(errorMessage(err)))
          }
        >
          Download all my data (JSON)
        </button>
      </div>
      <details>
        <summary className="error">Delete my account</summary>
        <p>This signs you out everywhere, unlinks chat apps, and permanently deletes your resumes, matches, applications, conversations and connected accounts.</p>
        <label>
          Type DELETE to confirm
          <input value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </label>
        <button
          type="button"
          className="danger"
          disabled={confirm !== "DELETE"}
          onClick={() =>
            void api
              .deleteAccount()
              .then(() => router.replace("/"))
              .catch((err) => setError(errorMessage(err)))
          }
        >
          Delete permanently
        </button>
      </details>
      <Notice kind="error">{error}</Notice>
    </div>
  );
}

export default function SettingsPage() {
  const profile = useLoad(() => api.profile());
  const [banner, setBanner] = useState<{ kind: "success" | "error" | "info"; text: string } | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected")) setBanner({ kind: "success", text: `Connected ${params.get("connected")}.` });
    else if (params.get("error")) setBanner({ kind: "error", text: `Connection failed (${params.get("error")}). Try again.` });
    else if (params.get("welcome")) setBanner({ kind: "info", text: "Welcome! Upload a resume under Resumes and tell me what roles you want here." });
  }, []);

  return (
    <section>
      <PageHead eyebrow="SETTINGS" title="Profile, connections and data" />
      {banner && <Notice kind={banner.kind}>{banner.text}</Notice>}
      <Notice kind="error">{profile.error}</Notice>
      {profile.data && <ProfileForm profile={profile.data} onSaved={(p) => profile.setData(p)} />}
      <EmailConnections />
      <Messaging />
      <DataControls />
    </section>
  );
}
