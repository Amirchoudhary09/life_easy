"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [phoneOtpSent, setPhoneOtpSent] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const response = await fetch(`${API}/api/v1/auth/${mode}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", ...(typeof document !== "undefined" && document.cookie.includes("life_easy_csrf=") ? { "X-CSRF-Token": decodeURIComponent(document.cookie.split("; ").find(x => x.startsWith("life_easy_csrf="))?.split("=")[1] || "") } : {}) },
        body: JSON.stringify(mode === "register" ? { display_name: name, email, password } : { email, password }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Unable to continue. Please try again.");
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }


  async function sendPhoneOtp() {
    setError(""); setBusy(true);
    try {
      const r = await fetch(API + "/api/v1/auth/phone/send", { method:"POST", credentials:"include", headers:{"Content-Type":"application/json"}, body:JSON.stringify({phone_e164:phone}) });
      const d = await r.json(); if(!r.ok) throw new Error(d.detail || "Unable to send OTP");
      setPhoneOtpSent(true); setError(d.message || "OTP sent if this number belongs to a verified account.");
    } catch(e) { setError(e instanceof Error ? e.message : "OTP request failed."); } finally { setBusy(false); }
  }
  async function verifyPhoneOtp() {
    setError(""); setBusy(true);
    try {
      const r = await fetch(API + "/api/v1/auth/phone/verify", { method:"POST", credentials:"include", headers:{"Content-Type":"application/json"}, body:JSON.stringify({phone_e164:phone,code:otp}) });
      const d = await r.json(); if(!r.ok) throw new Error(d.detail || "Invalid OTP");
      router.push("/dashboard");
    } catch(e) { setError(e instanceof Error ? e.message : "Phone login failed."); } finally { setBusy(false); }
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

      {mode === "login" && <section className="auth-phone">
        <p className="eyebrow">OR SIGN IN WITH PHONE OTP</p>
        <label>Mobile number (E.164)<input value={phone} onChange={e=>setPhone(e.target.value)} placeholder="+919876543210"/></label>
        {!phoneOtpSent ? <button type="button" className="primary auth-submit" disabled={busy || phone.length < 9} onClick={sendPhoneOtp}>Send OTP →</button> : <>
          <label>6-digit OTP<input value={otp} onChange={e=>setOtp(e.target.value)} maxLength={6} inputMode="numeric" placeholder="Enter OTP"/></label>
          <button type="button" className="primary auth-submit" disabled={busy || otp.length !== 6} onClick={verifyPhoneOtp}>Verify & log in →</button>
        </>}
      </section>}
      <p className="auth-foot">Your profile and career data are private to your account. Phone OTP sign-in requires a verified phone number and configured SMS provider.</p>
    </section>
    <p className="auth-back"><Link href="/">← Back to Life Easy</Link></p>
  </main>;
}
