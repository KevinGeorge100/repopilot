"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Arrow, Check, Close, Logo } from "@/components/ui/Icons";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { Button } from "@/components/ui/Button";
import type { RepoStatus } from "@/lib/types";

export function repoName(id: string): string {
  return id.replace("--", "/");
}

/** Share of vectors computed so far, or null once search is fully sharpened. */
export function sharpening(r: RepoStatus): number | null {
  const total = r.embed_total ?? 0;
  const done = r.embedded ?? 0;
  return r.status === "ready" && total > done ? Math.round((done / total) * 100) : null;
}

export function AppHeader({ repo, onHelp, onReset }: { repo: RepoStatus; onHelp: () => void; onReset: () => void }) {
  const pct = sharpening(repo);
  const ready = repo.status === "ready";
  return (
    <header className="glass sticky top-0 z-30 border-b border-line">
      <div className="mx-auto flex h-16 max-w-[110rem] items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Link href="/" className="flex shrink-0 items-center gap-2 rounded-md font-bold tracking-tight" aria-label="RepoPilot home">
            <Logo />
            <span className="hidden text-lg sm:inline">RepoPilot</span>
          </Link>
          <span aria-hidden className="hidden h-5 w-px bg-line sm:block" />
          <p className="flex min-w-0 items-center gap-2">
            <span className="truncate font-mono text-sm font-medium">{repoName(repo.id)}</span>
            {ready && pct === null && (
              <span className="pop inline-flex shrink-0 items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-xs font-semibold text-ink">
                <Check size={12} className="text-verified" /> <span className="sr-only sm:not-sr-only">Ready</span>
              </span>
            )}
            {!ready && repo.status !== "error" && (
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-surface-2 px-2 py-0.5 text-xs font-semibold text-muted">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" /> <span className="sr-only sm:not-sr-only">Getting ready</span>
              </span>
            )}
            {pct !== null && (
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-surface-2 px-2 py-0.5 text-xs font-semibold text-muted" title="You can ask now. Search keeps improving in the background.">
                <span className="h-1.5 w-1.5 rounded-full bg-marker" /> <span className="sr-only sm:not-sr-only">Sharpening {pct}%</span>
              </span>
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <span className="hidden sm:block">
            <Button variant="ghost" onClick={onHelp}>
              Help
            </Button>
          </span>
          <Button variant="secondary" onClick={onReset}>
            <span className="sm:hidden">Change</span>
            <span className="hidden sm:inline">Change repo</span>
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

const TIPS = [
  "Every answer ends in tags like signer.py:94-96. Click one to see those exact lines highlighted.",
  "Before an answer is shown, each tag is checked: the file exists, the lines exist, and the AI read them.",
  "Try “Where does execution start?” or “How does this handle errors?” for a quick tour.",
  "A struck-through tag means a check failed. Don’t rely on that claim.",
];

const STEPS = ["Download the code", "Read it", "Ready to ask"];

function stepIndex(r: RepoStatus): number {
  if (r.status === "ready") return 3;
  if (r.status === "chunking" || r.status === "embedding") return 1;
  return 0;
}

/** Shown while a repo is being fetched: honest progress, a clock, something to read, and the option to ask early. */
export function ProgressCard({ repo }: { repo: RepoStatus }) {
  const [secs, setSecs] = useState(0);
  const [tip, setTip] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const t = setInterval(() => setTip((i) => (i + 1) % TIPS.length), 5000);
    return () => clearInterval(t);
  }, []);
  const at = stepIndex(repo);
  return (
    <section className="card rise max-w-[44rem] p-5 sm:p-6" aria-labelledby="prog-h">
      <h2 id="prog-h" className="t-h3">
        Getting {repoName(repo.id)} ready
      </h2>
      <ol className="mt-4 space-y-3" aria-label="Progress">
        {STEPS.map((label, i) => {
          const done = i < at;
          const current = i === at;
          return (
            <li key={label} className="flex items-center gap-3">
              <span
                className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors duration-300 ${
                  done ? "bg-verified/15 text-verified" : current ? "bg-primary text-on-primary" : "bg-surface-2 text-muted"
                }`}
              >
                {done ? <Check size={14} /> : current ? <span className="h-2 w-2 animate-pulse rounded-full bg-on-primary" /> : i + 1}
              </span>
              <span className={done ? "text-muted" : current ? "font-semibold" : "text-muted"}>
                {label}
                {current && repo.status === "queued" && i === 0 ? " (waiting for another repo to finish)" : ""}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <div className="h-full rounded-full bg-primary transition-[width] duration-700" style={{ width: `${Math.max(8, (at / 3) * 100)}%` }} />
      </div>
      <p className="t-small mt-3 text-muted" role="status" aria-live="polite">
        {secs < 20 ? `${secs}s. Usually a few seconds.` : `${secs}s. Still working: big repos take longer, and this free server is small. You can already type a question below.`}
      </p>
      <p key={tip} className="rise mt-4 border-t border-line pt-4 text-[0.95rem] text-muted">
        <span className="font-semibold text-ink">Meanwhile: </span>
        {TIPS[tip]}
      </p>
    </section>
  );
}

type ComposerProps = {
  value: string;
  onChange: (v: string) => void;
  onSend: (q: string) => void;
  busy: boolean;
  ready: boolean;
  liveOff: boolean;
};

export function Composer({ value, onChange, onSend, busy, ready, liveOff }: ComposerProps) {
  return (
    <form
      className="safe-bottom sticky bottom-0 z-10 border-t border-line bg-bg/95 px-4 pt-3 shadow-[0_-12px_24px_-16px_rgb(14_19_48/0.25)] backdrop-blur sm:px-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim().length >= 3) onSend(value);
      }}
    >
      {liveOff && <p className="t-small mb-2 max-w-[68ch] text-muted">Live questions are unavailable right now (no model is configured or today’s limit was reached). The example questions still work.</p>}
      <div className="flex max-w-[68ch] gap-2">
        <label className="sr-only" htmlFor="q">
          Your question
        </label>
        <input
          id="q"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={liveOff ? "Live questions are unavailable" : ready ? "Ask your own question about this code" : "Type a question now. I’ll ask it the moment the repo is ready"}
          disabled={liveOff}
          maxLength={1000}
          autoComplete="off"
          enterKeyHint="send"
          className="min-h-12 min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-4 text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-primary/20 disabled:bg-surface-2"
        />
        <Button type="submit" size="lg" disabled={busy || liveOff || value.trim().length < 3} aria-label="Ask">
          <span className="hidden sm:inline">{ready ? "Ask" : "Queue"}</span>
          <Arrow size={18} />
        </Button>
      </div>
    </form>
  );
}

/** Evidence column on laptops; a slide-up sheet on phones. */
export function EvidenceSheet({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  return (
    <>
      <div
        aria-hidden
        onClick={onClose}
        className={`fixed inset-0 z-30 bg-ink/50 transition-opacity duration-300 lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
      />
      <aside
        aria-label="Source code evidence"
        className={`fixed inset-x-0 bottom-0 z-40 flex h-[78dvh] flex-col overflow-hidden rounded-t-2xl border border-line bg-surface shadow-[var(--shadow-lg)] transition-transform duration-300 ease-out lg:sticky lg:top-16 lg:z-0 lg:h-[calc(100dvh-4rem)] lg:translate-y-0 lg:rounded-none lg:border-y-0 lg:border-r-0 lg:shadow-none ${
          open ? "translate-y-0" : "translate-y-full"
        }`}
      >
        <div className="flex justify-center pt-2 lg:hidden" aria-hidden>
          <span className="h-1 w-10 rounded-full bg-line-strong" />
        </div>
        {children}
      </aside>
    </>
  );
}

export function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1800);
        } catch {
          /* clipboard blocked: nothing to confirm */
        }
      }}
      className="press inline-flex min-h-11 items-center gap-2 rounded-md px-3 text-sm text-muted hover:bg-surface-2 hover:text-ink"
    >
      {done ? <Check size={16} className="text-verified" /> : null}
      <span aria-live="polite">{done ? "Copied" : "Copy answer"}</span>
    </button>
  );
}

export { Close };
