"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnswerView } from "@/components/AnswerView";
import { Button } from "@/components/ui/Button";
import { ReadingTips } from "@/components/Guide";
import { AppHeader, Composer, CopyButton, EvidenceSheet, ProgressCard, repoName, sharpening } from "@/components/app/AppParts";
import { EvidencePanel } from "@/components/EvidencePanel";
import { Landing } from "@/components/Landing";
import { Trail } from "@/components/Trail";
import { friendlyError } from "@/lib/errors";
import { ask, getConfig, getRepo, startIndex } from "@/lib/api";
import type { Citation, Config, RepoStatus, Turn } from "@/lib/types";
import { citeKey } from "@/lib/types";

const STARTERS = [
  "What does this project do, in plain English?",
  "Give me a tour of how this project is organised.",
  "Where does execution start, and what happens next?",
  "How does this project handle errors?",
];

function toUrl(input: string): string | null {
  const s = input.trim().replace(/^https?:\/\//, "").replace(/^github\.com\//, "").replace(/\.git$/, "").replace(/\/$/, "");
  return /^[\w.-]+\/[\w.-]+$/.test(s) ? `https://github.com/${s}` : null;
}

export default function Home() {
  const [input, setInput] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [repo, setRepo] = useState<RepoStatus | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [active, setActive] = useState<{ turn: number; cite: Citation } | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [config, setConfig] = useState<Config | null>(null);
  const [showTips, setShowTips] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const busy = turns.some((t) => t.status === "working");

  useEffect(() => {
    getConfig().then(setConfig);
  }, []);

  // Poll indexing progress.
  useEffect(() => {
    if (!repo || repo.status === "error") return;
    const searching = repo.status === "ready" && (repo.embed_total ?? 0) > (repo.embedded ?? 0);
    if (repo.status === "ready" && !searching) return;
    const t = setTimeout(async () => {
      try {
        setRepo(await getRepo(repo.id));
      } catch (e) {
        setRepo({ ...repo, status: "error", error: (e as Error).message });
      }
    }, searching ? 2500 : 700);
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

  const runTurn = useCallback(async (id: number, q: string, repoId: string) => {
    const patch = (fn: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)));
    patch((t) => ({ ...t, status: "working" }));
    abort.current = new AbortController();
    try {
      await ask(
        repoId,
        q,
        {
          onToolCall: (name, inp) => patch((t) => ({ ...t, steps: [...t.steps, { name, input: inp, done: false, failed: false }] })),
          onToolResult: (_n, error) =>
            patch((t) => ({ ...t, steps: t.steps.map((s, i) => (i === t.steps.length - 1 ? { ...s, done: true, failed: error } : s)) })),
          onRepair: () => patch((t) => ({ ...t, repairing: true })),
          onAnswer: (a) => patch((t) => ({ ...t, answer: a, status: "done", repairing: false })),
          onError: (m) => patch((t) => ({ ...t, status: "error", error: friendlyError(m) })),
        },
        abort.current.signal,
      );
      patch((t) => (t.status === "working" ? { ...t, status: "error", error: "The connection closed before an answer arrived." } : t));
    } catch (e) {
      if ((e as Error).name !== "AbortError") patch((t) => ({ ...t, status: "error", error: friendlyError((e as Error).message) }));
    }
  }, []);

  // A question asked before the repo is ready is queued, then sent automatically the moment it is.
  const send = useCallback(
    (q: string) => {
      if (!repo || q.trim().length < 3) return;
      const id = Date.now();
      setQuestion("");
      setTurns((ts) => [...ts, { id, question: q.trim(), steps: [], repairing: false, status: repo.status === "ready" ? "working" : "queued" }]);
      if (repo.status === "ready") runTurn(id, q.trim(), repo.id);
    },
    [repo, runTurn],
  );

  useEffect(() => {
    if (repo?.status !== "ready" || turns.some((t) => t.status === "working")) return;
    const next = turns.find((t) => t.status === "queued");
    if (next) runTurn(next.id, next.question, repo.id);
  }, [repo, turns, runTurn]);

  const reset = () => {
    abort.current?.abort();
    setRepo(null);
    setTurns([]);
    setActive(null);
    setPanelOpen(false);
  };

  const examples = config?.repos.find((r) => r.id === repo?.id)?.examples ?? [];
  const liveOff = config !== null && (!config.live_questions || config.daily_remaining === 0);

  const sources: Citation[] = (() => {
    const t = turns.find((x) => x.id === active?.turn);
    const seen = new Set<string>();
    return (t?.answer?.citations.valid ?? []).filter((c) => !seen.has(citeKey(c)) && seen.add(citeKey(c)));
  })();

  // ---- Landing ----
  if (!repo) {
    return <Landing config={config} input={input} setInput={setInput} formError={formError} onOpen={open} />;
  }

  const ready = repo.status === "ready";
  const failed = repo.status === "error";
  const pct = sharpening(repo);
  const starters = examples.length > 0 ? examples : STARTERS;

  return (
    <>
      <AppHeader repo={repo} onHelp={() => setShowTips((v) => !v)} onReset={reset} />
      <div className="mx-auto grid max-w-[110rem] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,34rem)] xl:grid-cols-[15rem_minmax(0,1fr)_minmax(0,36rem)]">
        <nav aria-label="This repository" className="hidden border-r border-line px-5 py-8 xl:block">
          <div className="sticky top-24 space-y-6 text-sm">
            <div>
              <p className="font-mono text-sm font-semibold">{repoName(repo.id)}</p>
              <p className="mt-1 text-muted">{ready ? `${repo.chunks.toLocaleString()} pieces of code indexed` : "Getting ready…"}</p>
              {pct !== null && <p className="mt-1 text-muted">Search sharpening: {pct}%</p>}
            </div>
            <div>
              <p className="font-semibold">Try asking</p>
              <ul className="mt-2 space-y-1">
                {starters.slice(0, 4).map((q) => (
                  <li key={q}>
                    <button onClick={() => send(q)} disabled={busy} className="press w-full rounded-md px-2 py-2 text-left text-link hover:bg-surface-2 disabled:text-muted">
                      {q}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </nav>

        <main id="main" className="flex min-h-[calc(100dvh-4rem)] min-w-0 flex-col">
          <div className="flex-1 px-4 pb-8 pt-6 sm:px-6 sm:pt-8">
            {failed && (
              <section role="alert" className="card max-w-[44rem] p-6">
                <h2 className="t-h3">Couldn’t open {repoName(repo.id)}</h2>
                <p className="mt-2 text-muted">{repo.error ?? "Something went wrong."}</p>
                <div className="mt-5 flex flex-wrap gap-3">
                  <Button onClick={reset}>Choose another repo</Button>
                </div>
              </section>
            )}
            {!failed && !ready && <ProgressCard repo={repo} />}
            {(turns.length > 0 || showTips) && <ReadingTips forceOpen={showTips} onDismiss={() => setShowTips(false)} />}
            {!failed && repo.truncated && ready && (
              <p className="t-small mb-4 max-w-[68ch] text-muted">
                This repo is large, so only the {repo.chunks.toLocaleString()} most relevant pieces of code were indexed. Docs and changelogs were dropped first.
              </p>
            )}
            {!failed && turns.length === 0 && (
              <div className={`max-w-[68ch] ${ready ? "" : "mt-8"}`}>
                <h1 className="t-h2">{ready ? "What do you want to know?" : "While it loads, pick a question"}</h1>
                <p className="mt-2 text-muted">
                  {!ready
                    ? "Click one and it will be asked the moment the repo is ready."
                    : examples.length > 0
                      ? "These examples load instantly: their answers are real results saved from a test run. Anything you type is answered live."
                      : "Click one, or type your own below."}
                </p>
                <ul className="mt-5 grid gap-2 sm:grid-cols-2">
                  {starters.map((q, i) => (
                    <li key={q} className="rise" style={{ "--d": i } as React.CSSProperties}>
                      <button
                        onClick={() => send(q)}
                        className="card press lift w-full px-4 py-3 text-left font-serif text-[1.05rem] leading-snug text-link"
                      >
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {turns.length > 0 && <h1 className="sr-only">Questions about {repoName(repo.id)}</h1>}
            {turns.map((t) => (
              <section key={t.id} className="mb-10 max-w-[68ch]" aria-label={t.question}>
                <h2 className="rise mt-8 text-xl font-semibold leading-snug tracking-tight">{t.question}</h2>
                {t.status === "queued" && (
                  <div role="status" className="mt-3">
                    <p className="text-muted">Queued. I’ll ask this as soon as the repo is ready.</p>
                    <div className="skeleton mt-3 h-3.5 w-3/4" aria-hidden />
                  </div>
                )}
                <Trail steps={t.steps} working={t.status === "working"} repairing={t.repairing} />
                {t.status === "working" && t.steps.length === 0 && (
                  <div className="mt-2 space-y-2.5" aria-hidden>
                    <div className="skeleton h-3.5 w-[90%]" />
                    <div className="skeleton h-3.5 w-[70%]" />
                  </div>
                )}
                {t.status === "error" && (
                  <p role="alert" className="text-alert">
                    {t.error}
                  </p>
                )}
                {t.answer && (
                  <div className="rise">
                    <AnswerView
                      payload={t.answer}
                      active={active?.turn === t.id ? active.cite : null}
                      onOpen={(c) => {
                        setActive({ turn: t.id, cite: c });
                        setPanelOpen(true);
                      }}
                    />
                    <div className="mt-1 -ml-3">
                      <CopyButton text={t.answer.answer} />
                    </div>
                  </div>
                )}
              </section>
            ))}
            <div ref={endRef} />
          </div>
          <Composer value={question} onChange={setQuestion} onSend={send} busy={busy} ready={ready} liveOff={liveOff && ready} />
        </main>

        <EvidenceSheet open={panelOpen} onClose={() => setPanelOpen(false)}>
          <EvidencePanel
            repo={repo.id}
            sources={sources}
            active={active?.cite ?? null}
            onSelect={(c) => active && setActive({ turn: active.turn, cite: c })}
            onClose={() => setPanelOpen(false)}
          />
        </EvidenceSheet>
      </div>
    </>
  );
}
