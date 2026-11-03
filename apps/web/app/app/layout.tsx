"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/app", label: "Chat" },
  { href: "/app/matches", label: "Matches" },
  { href: "/app/jobs", label: "Jobs" },
  { href: "/app/tracker", label: "Tracker" },
  { href: "/app/approvals", label: "Approvals" },
  { href: "/app/resumes", label: "Resumes" },
  { href: "/app/settings", label: "Settings" },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const { ready, user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  if (!ready || !user) {
    return (
      <main className="shell">
        <p className="loading">Loading…</p>
      </main>
    );
  }

  return (
    <div className="app">
      <header className="app-bar">
        <div className="app-bar-inner">
          <Link className="brand" href="/app">
            life<span>easy</span>
          </Link>
          <nav className="tabs" aria-label="Sections">
            {NAV.map((item) => {
              const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
              return (
                <Link key={item.href} href={item.href} className={active ? "tab active" : "tab"} aria-current={active ? "page" : undefined}>
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="row user">
            <span className="muted">{user.display_name || user.email}</span>
            <button
              type="button"
              className="ghost"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
            >
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
