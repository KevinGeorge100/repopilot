"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnswerView } from "@/components/AnswerView";
import { EvidencePanel } from "@/components/EvidencePanel";
import { Trail } from "@/components/Trail";
import { ask, getRepo, startIndex } from "@/lib/api";
import type { Citation, RepoStatus, Turn } from "@/lib/types";
import { citeKey } from "@/lib/types";

const EXAMPLES = ["pallets/itsdangerous", "pallets/click"];
const STARTERS = [
  "Give me a tour of how this project is organised.",
  "Where does execution start, and what happens next?",
  "How does this project handle errors?",
];

function toUrl(input: string): string | null {
  const s = input.trim().replace(/^https?:\/\//, "").replace(/^github\.com\//, "").replace(/\.git$/, "").replace(/\/$/, "");
  return /^[\w.-]+\/[\w.-]+$/.test(s) ? `https://github.com/${s}` : null;
}

function phaseText(r: RepoStatus): string {
  if (r.status === "queued" || r.status === "cloning") return "Downloading the repository";
  if (r.status === "chunking") return "Splitting source files into functions and classes";
  if (r.status === "embedding") return `Indexing code: ${r.done} of ${r.total} pieces`;
  return "";
}

export default function Home() {
  const [input, setInput] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [repo, setRepo] = useState<RepoStatus | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [active, setActive] = useState<{ turn: number; cite: Citation } | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const busy = turns.some((t) => t.status === "working");

  // Poll indexing progress.
  useEffect(() => {
    if (!repo || repo.status === "ready" || repo.status === "error") return;
    const t = setTimeout(async () => {
      try {
        setRepo(await getRepo(repo.id));
      } catch (e) {
        setRepo({ ...repo, status: "error", error: (e as Error).message });
      }
    }, 1200);
    return () => clearTimeout(t);
  }, [repo]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns]);

  useEffect(() => () => abort.current?.abort(), []);

  const open = useCallback(async (raw: string) => {
    const url = toUrl(raw);
    if (!url) {
      setFormError("Enter a public repo as owner/name, like pallets/click.");
      return;
    }
    setFormError(null);
    setTurns([]);
    setActive(null);
    try {
      setRepo(await startIndex(url));
    } catch (e) {
      setFormError((e as Error).message);
    }
  }, []);

  const send = useCallback(
    async (q: string) => {
      if (!repo || !q.trim() || busy) return;
      const id = Date.now();
      setQuestion("");
      setTurns((ts) => [...ts, { id, question: q.trim(), steps: [], repairing: false, status: "working" }]);
      const patch = (fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)));
      abort.current = new AbortController();
      try {
        await ask(
          repo.id,
          q.trim(),
          {
            onToolCall: (name, inp) =>
              patch((t) => ({ ...t, steps: [...t.steps, { name, input: inp, done: false, failed: false }] })),
            onToolResult: (_n, error) =>
              patch((t) => ({
                ...t,
                steps: t.steps.map((s, i) => (i === t.steps.length - 1 ? { ...s, done: true, failed: error } : s)),
              })),
            onRepair: () => patch((t) => ({ ...t, repairing: true })),
            onAnswer: (a) => patch((t) => ({ ...t, answer: a, status: "done", repairing: false })),
            onError: (m) => patch((t) => ({ ...t, status: "error", error: m })),
          },
          abort.current.signal,
        );
        patch((t) => (t.status === "working" ? { ...t, status: "error", error: "The connection closed before an answer arrived." } : t));
      } catch (e) {
        if ((e as Error).name !== "AbortError") patch((t) => ({ ...t, status: "error", error: (e as Error).message }));
      }
    },
    [repo, busy],
  );

  const reset = () => {
    abort.current?.abort();
    setRepo(null);
    setTurns([]);
    setActive(null);
    setPanelOpen(false);
  };

  const sources: Citation[] = (() => {
    const t = turns.find((x) => x.id === active?.turn);
    const seen = new Set<string>();
    return (t?.answer?.citations.valid ?? []).filter((c) => !seen.has(citeKey(c)) && seen.add(citeKey(c)));
  })();

  // ---- Landing ----
  if (!repo) {
    return (
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-4 py-16 sm:px-6">
        <p className="mb-10 text-xl font-bold tracking-tight">RepoPilot</p>
        <h1 className="max-w-[18ch] text-4xl font-bold leading-[1.08] tracking-tight sm:text-6xl">
          Ask a repo anything. See the lines behind every answer.
        </h1>
        <p className="mt-5 max-w-[52ch] font-serif text-xl leading-relaxed text-graphite">
          Paste a public GitHub repository. RepoPilot reads the code, answers your question, and checks that every
          citation points to real lines it actually read.
        </p>
        <form
          className="mt-9 flex flex-col gap-3 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            open(input);
          }}
        >
          <label className="sr-only" htmlFor="repo">
            GitHub repository
          </label>
          <input
            id="repo"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="github.com/owner/repo"
            autoComplete="off"
            spellCheck={false}
            className="min-w-0 flex-1 rounded-md border border-rule bg-sheet px-4 py-3 font-mono text-sm outline-none focus:border-cobalt"
          />
          <button
            type="submit"
            className="rounded-md bg-ink px-6 py-3 font-semibold text-sheet transition hover:bg-cobalt-ink"
          >
            Open repo
          </button>
        </form>
        {formError && (
          <p role="alert" className="mt-3 text-alert">
            {formError}
          </p>
        )}
        <p className="mt-6 text-graphite">
          Try{" "}
          {EXAMPLES.map((ex, i) => (
            <span key={ex}>
              {i > 0 && " or "}
              <button type="button" onClick={() => open(ex)} className="font-mono text-sm text-cobalt-ink underline underline-offset-4">
                {ex}
              </button>
            </span>
          ))}
        </p>
        <p className="mt-16 max-w-[58ch] text-sm text-graphite">
          Public repositories only. Code snippets are sent to an AI provider to write each answer, so don’t open
          anything private.
        </p>
      </main>
    );
  }

  // ---- Indexing / error ----
  if (repo.status !== "ready") {
    const failed = repo.status === "error";
    const pct = repo.status === "embedding" && repo.total ? Math.round((repo.done / repo.total) * 100) : null;
    return (
      <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-4 sm:px-6">
        <p className="mb-8 text-xl font-bold tracking-tight">RepoPilot</p>
        <h1 className="font-mono text-lg font-medium">{repo.id.replace("--", "/")}</h1>
        {failed ? (
          <div role="alert" className="mt-4">
            <p className="text-alert">Couldn’t open this repository.</p>
            <p className="mt-1 text-graphite">{repo.error ?? "Something went wrong."} Check the name is a public repo and try again.</p>
            <button onClick={reset} className="mt-5 rounded-md bg-ink px-5 py-2.5 font-semibold text-sheet">
              Choose another repo
            </button>
          </div>
        ) : (
          <div className="mt-4" role="status" aria-live="polite">
            <p className="text-graphite">{phaseText(repo)}</p>
            <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-rule">
              <div
                className={`h-full rounded-full bg-cobalt transition-all duration-500 ${pct === null ? "w-1/4 animate-pulse" : ""}`}
                style={pct === null ? undefined : { width: `${pct}%` }}
              />
            </div>
            <p className="mt-3 text-sm text-graphite">Large repositories can take a few minutes the first time.</p>
          </div>
        )}
      </main>
    );
  }

  // ---- Chat + evidence ----
  return (
    <div className="lg:grid lg:min-h-screen lg:grid-cols-[minmax(0,1fr)_34rem]">
      <main className="flex min-h-screen min-w-0 flex-col">
        <header className="flex items-center justify-between gap-4 px-4 py-4 sm:px-8">
          <p className="text-lg font-bold tracking-tight">RepoPilot</p>
          <div className="flex min-w-0 items-center gap-3 text-sm">
            <span className="truncate font-mono">{repo.id.replace("--", "/")}</span>
            <button onClick={reset} className="shrink-0 text-cobalt-ink underline underline-offset-4">
              Change repo
            </button>
          </div>
        </header>

        <div className="flex-1 px-4 pb-6 sm:px-8">
          {repo.truncated && (
            <p className="mb-4 max-w-[68ch] text-sm text-graphite">
              This repo is large, so only the {repo.chunks.toLocaleString()} most relevant pieces of code were indexed. Docs and changelogs were
              dropped first.
            </p>
          )}
          {turns.length === 0 && (
            <div className="max-w-[68ch] pt-8">
              <h1 className="text-3xl font-bold tracking-tight">What do you want to know?</h1>
              <ul className="mt-5 flex flex-col items-start gap-2">
                {STARTERS.map((s) => (
                  <li key={s}>
                    <button onClick={() => send(s)} className="text-left font-serif text-lg text-cobalt-ink underline decoration-rule underline-offset-4 hover:decoration-cobalt">
                      {s}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {turns.map((t) => (
            <section key={t.id} className="mb-10 max-w-[68ch]" aria-label={t.question}>
              <h2 className="mt-8 text-xl font-semibold leading-snug tracking-tight">{t.question}</h2>
              <Trail steps={t.steps} working={t.status === "working"} repairing={t.repairing} />
              {t.status === "error" && (
                <p role="alert" className="text-alert">
                  {t.error} <span className="text-graphite">Ask again in a moment.</span>
                </p>
              )}
              {t.answer && (
                <AnswerView
                  payload={t.answer}
                  active={active?.turn === t.id ? active.cite : null}
                  onOpen={(c) => {
                    setActive({ turn: t.id, cite: c });
                    setPanelOpen(true);
                  }}
                />
              )}
            </section>
          ))}
          <div ref={endRef} />
        </div>

        <form
          className="sticky bottom-0 border-t border-rule bg-paper/95 px-4 py-3 backdrop-blur sm:px-8"
          onSubmit={(e) => {
            e.preventDefault();
            send(question);
          }}
        >
          <div className="flex max-w-[68ch] gap-2">
            <label className="sr-only" htmlFor="q">
              Your question
            </label>
            <input
              id="q"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about this code"
              maxLength={1000}
              autoComplete="off"
              className="min-w-0 flex-1 rounded-md border border-rule bg-sheet px-4 py-2.5 outline-none focus:border-cobalt"
            />
            <button
              type="submit"
              disabled={busy || question.trim().length < 3}
              className="rounded-md bg-ink px-5 py-2.5 font-semibold text-sheet transition hover:bg-cobalt-ink disabled:bg-rule disabled:text-graphite"
            >
              {busy ? "Working" : "Ask"}
            </button>
          </div>
        </form>
      </main>

      <aside
        aria-label="Source code evidence"
        className={`border-rule bg-sheet lg:sticky lg:top-0 lg:block lg:h-screen lg:border-l ${
          panelOpen ? "fixed inset-0 z-20 block" : "hidden"
        }`}
      >
        <EvidencePanel
          repo={repo.id}
          sources={sources}
          active={active?.cite ?? null}
          onSelect={(c) => active && setActive({ turn: active.turn, cite: c })}
          onClose={() => setPanelOpen(false)}
        />
      </aside>
    </div>
  );
}
