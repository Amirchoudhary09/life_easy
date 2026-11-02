"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const response = await fetch(`${API}/api/v1/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mode === "register" ? { display_name: name, email, password } : { email, password }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Unable to continue. Please try again.");
      sessionStorage.setItem("life_easy_token", data.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-shell">
    <Link className="brand" href="/">life<span>easy</span></Link>
    <section className="auth-card">
      <p className="eyebrow">CAREER-FIRST AI ASSISTANT</p>
      <h1>{mode === "login" ? "Welcome back." : "Build your career workspace."}</h1>
      <p className="auth-copy">Find opportunities, organize applications, and prepare career communication with AI.</p>
      <div className="auth-switch">
        <button className={mode === "login" ? "selected" : ""} onClick={() => setMode("login")} type="button">Log in</button>
        <button className={mode === "register" ? "selected" : ""} onClick={() => setMode("register")} type="button">Create account</button>
      </div>
      <form onSubmit={submit} className="auth-form">
        {mode === "register" && <label>Full name<input required minLength={1} maxLength={100} value={name} onChange={e => setName(e.target.value)} placeholder="Your name"/></label>}
        <label>Email address<input required type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com"/></label>
        <label>Password<input required type="password" minLength={mode === "register" ? 12 : 1} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} placeholder={mode === "register" ? "At least 12 characters" : "Your password"}/></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary auth-submit" disabled={busy}>{busy ? "Please wait..." : mode === "login" ? "Log in" : "Create my account"} <span>→</span></button>
      </form>
      <p className="auth-foot">Your profile and career data are private to your account. Email verification will be enabled after the email provider is configured.</p>
    </section>
    <p className="auth-back"><Link href="/">← Back to Life Easy</Link></p>
  </main>;
}
