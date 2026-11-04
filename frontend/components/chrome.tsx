"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { FlaskConical, History, List, Plus } from "lucide-react";
import { getJSON } from "@/lib/api";

type Health = { status: string; ai_configured: boolean; product: string };

type ToastApi = { push: (text: string) => void };
type TitleApi = { setTitle: (title: string) => void };

const ToastContext = createContext<ToastApi>({ push: () => undefined });
const TitleContext = createContext<TitleApi>({ setTitle: () => undefined });

export function useToast() {
  return useContext(ToastContext);
}

export function usePageTitle(title: string) {
  const { setTitle } = useContext(TitleContext);
  useEffect(() => {
    setTitle(title);
    document.title = title ? `${title} · PatchProof` : "PatchProof";
    return () => {
      setTitle("");
      document.title = "PatchProof";
    };
  }, [setTitle, title]);
}

const NAV = [
  { href: "/", label: "Overview", icon: List },
  { href: "/new", label: "New review", icon: Plus },
  { href: "/history", label: "Review history", icon: History },
  { href: "/evaluation", label: "Evaluation", icon: FlaskConical },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);

  const push = useMemo(
    () => (text: string) => {
      const id = Date.now() + Math.random();
      setToasts((current) => [...current, { id, text }]);
      window.setTimeout(() => {
        setToasts((current) => current.filter((item) => item.id !== id));
      }, 3200);
    },
    [],
  );

  const checkHealth = useCallback(() => {
    setHealthError(false);
    getJSON<Health>("/api/health")
      .then(setHealth)
      .catch(() => setHealthError(true));
  }, []);

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "n") {
        event.preventDefault();
        router.push("/new");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  const review = path.startsWith("/review/");
  const crumbs = crumbsFor(path, title);

  return (
    <ToastContext.Provider value={{ push }}>
      <TitleContext.Provider value={{ setTitle }}>
        <div className="app">
          <aside className="sidebar">
            <Link href="/" className="brand">
              <Mark />
              <span>
                <strong>PatchProof</strong>
                <em>Evidence before opinion.</em>
              </span>
            </Link>
            <nav className="nav" aria-label="Primary">
              {NAV.map((item) => {
                const active = item.href === "/" ? path === "/" : path === item.href || path.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <Link key={item.href} href={item.href} className={active ? "nav-link active" : "nav-link"} aria-current={active ? "page" : undefined}>
                    <Icon size={18} strokeWidth={1.75} />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <div className="side-foot">
              <p title={healthError ? "The API did not respond" : "GET /api/health"}>
                <i className={healthError ? "dot bad" : "dot ok"} />
                {healthError ? "Engine unreachable" : health ? "Engine online" : "Checking engine"}
              </p>
              <p title="Whether OPENAI_API_KEY is set on the API">
                <i className={health?.ai_configured ? "dot ok" : "dot"} />
                {health?.ai_configured ? "AI key set" : "AI key not set"}
              </p>
              {healthError && <button type="button" className="btn" onClick={checkHealth}>Retry</button>}
              <p className="mono dim">0.1.0</p>
            </div>
          </aside>
          <div className={review ? "stage stage-review" : "stage"}>
            <header className="topbar">
              <nav className="crumbs" aria-label="Breadcrumb">
                {crumbs.map((crumb, index) => (
                  <span key={crumb.label}>
                    {index > 0 && <span className="sep">/</span>}
                    {crumb.href ? <Link href={crumb.href}>{crumb.label}</Link> : <span>{crumb.label}</span>}
                  </span>
                ))}
              </nav>
              <Link href="/new" className="btn primary top-action">
                New review
                <kbd>N</kbd>
              </Link>
            </header>
            <div className="stage-body">{children}</div>
          </div>
          <div className="toasts" aria-live="polite">
            {toasts.map((toast) => (
              <p key={toast.id} className="toast">
                {toast.text}
              </p>
            ))}
          </div>
        </div>
      </TitleContext.Provider>
    </ToastContext.Provider>
  );
}

function crumbsFor(path: string, title: string) {
  if (path === "/") return [{ label: "Overview" }];
  if (path === "/new") return [{ label: "Overview", href: "/" }, { label: "New review" }];
  if (path === "/history") return [{ label: "Overview", href: "/" }, { label: "History" }];
  if (path === "/evaluation") return [{ label: "Overview", href: "/" }, { label: "Evaluation" }];
  if (path.startsWith("/review/")) {
    return [
      { label: "Overview", href: "/" },
      { label: "History", href: "/history" },
      { label: title || "Review" },
    ];
  }
  return [{ label: "PatchProof" }];
}

function Mark() {
  return (
    <svg className="mark" width="18" height="18" viewBox="0 0 18 18" aria-hidden>
      <path d="M9 2.2v13.6" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="9" cy="4" r="1.7" fill="currentColor" />
      <circle cx="9" cy="9" r="1.7" fill="currentColor" />
      <circle cx="9" cy="14" r="1.7" fill="currentColor" />
    </svg>
  );
}
