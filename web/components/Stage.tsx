"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnswerView } from "@/components/AnswerView";
import { Arrow } from "@/components/ui/Icons";
import { Button } from "@/components/ui/Button";
import { friendlyError } from "@/lib/errors";
import { ask, getLines, type FileWindow } from "@/lib/api";
import type { AnswerPayload, Citation, DemoRepo } from "@/lib/types";

const CONTEXT = 9;

/** Plain-language size label so a newcomer knows where to start. */
function level(chunks: number): string {
  if (chunks < 100) return "Tiny";
  if (chunks < 500) return "Small";
  return "Bigger";
}

export function CodeWindow({ repo, cite }: { repo: string; cite: Citation | null }) {
  const [win, setWin] = useState<FileWindow | null>(null);
  const [err, setErr] = useState(false);
  const hit = useRef<HTMLDivElement | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const key = cite ? `${cite.path}:${cite.start}-${cite.end}` : "";

  useEffect(() => {
    if (!cite) return;
    let live = true;
    getLines(repo, cite.path, Math.max(1, cite.start - CONTEXT), cite.end + CONTEXT)
      .then((w) => live && (setWin(w), setErr(false)))
      .catch(() => live && (setErr(true), setWin(null)));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo, key]);

  // Scroll only inside the code window. scrollIntoView would also scroll the whole page, which is jarring
  // when an answer arrives while the visitor is reading something else.
  useEffect(() => {
    if (box.current && hit.current) box.current.scrollTop = Math.max(0, hit.current.offsetTop - 72);
  }, [win]);

  let first = true;
  let n = -1;
  return (
    <div className="flex h-full min-h-[18rem] flex-col overflow-hidden rounded-lg bg-night text-sm shadow-[var(--shadow-lg)] ring-1 ring-white/5">
      <div className="flex items-baseline justify-between gap-3 border-b border-white/10 px-4 py-2.5">
        <span className="truncate font-mono text-xs text-code-ink" title={cite?.path}>
          {cite ? cite.path : "The source code appears here"}
        </span>
        {cite && (
          <span className="shrink-0 font-mono text-xs text-marker">
            lines {cite.start}
            {cite.end !== cite.start ? `–${cite.end}` : ""}
          </span>
        )}
      </div>
      <div ref={box} tabIndex={0} role="region" aria-label={cite ? `Source code: ${cite.path}` : "Source code"} className="relative min-h-0 flex-1 overflow-auto py-2 font-mono text-[0.8rem] leading-6" aria-live="polite">
        {!cite && <p className="max-w-[30ch] px-5 py-8 font-sans text-base text-code-ink">Pick a question, then click a tag in the answer. The lines it came from get marked here.</p>}
        {cite && err && <p className="px-5 py-8 font-sans text-code-ink">Couldn’t load those lines. Try another tag.</p>}
        {cite && !err && !win && (
          <div className="space-y-2 px-5 py-4" aria-hidden>
            {[60, 85, 40, 72].map((w) => (
              <div key={w} className="skeleton h-3 opacity-30" style={{ width: `${w}%` }} />
            ))}
          </div>
        )}
        {win &&
          win.lines.map((text, i) => {
            const ln = win.start + i;
            const isHit = cite !== null && ln >= cite.start && ln <= cite.end;
            if (isHit) n += 1;
            const ref = isHit && first ? ((first = false), hit) : undefined;
            return (
              <div key={`${key}-${ln}`} ref={ref} className="code-line" data-hit={isHit} style={isHit ? ({ "--i": n } as React.CSSProperties) : undefined}>
                <span className="gutter">{ln}</span>
                <span>{text || " "}</span>
              </div>
            );
          })}
      </div>
    </div>
  );
}

type Props = { repos: DemoRepo[]; liveOff: boolean; onOpenFull: (name: string) => void };

export function Stage({ repos, liveOff, onOpenFull }: Props) {
  const sorted = [...repos].sort((a, b) => a.chunks - b.chunks);
  const [repoId, setRepoId] = useState(sorted[0]?.id ?? "");
  const [q, setQ] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, AnswerPayload | "loading" | { error: string }>>({});
  const [typed, setTyped] = useState("");
  const [cite, setCite] = useState<Citation | null>(null);
  const touched = useRef(false);
  const cache = useRef(answers);
  cache.current = answers;
  const repo = repos.find((r) => r.id === repoId) ?? sorted[0];

  const choose = useCallback(async (id: string, question: string, auto = false) => {
    if (!auto) touched.current = true;
    const k = `${id}|${question}`;
    setRepoId(id);
    setQ(question);
    setCite(null);
    const have = cache.current[k];
    if (have && have !== "loading" && !("error" in have)) {
      setCite(have.citations.valid[0] ?? null);
      return;
    }
    setAnswers((a) => ({ ...a, [k]: "loading" }));
    let got: AnswerPayload | null = null;
    let failure = "Couldn’t get an answer. Try another question.";
    try {
      await ask(id, question, {
        onToolCall: () => {},
        onToolResult: () => {},
        onRepair: () => {},
        onAnswer: (p) => (got = p),
        onError: (m) => (failure = friendlyError(m)),
      });
    } catch (e) {
      failure = friendlyError((e as Error).message);
    }
    const ans = got as AnswerPayload | null;
    setAnswers((a) => ({ ...a, [k]: ans ?? { error: failure } }));
    if (ans && !(auto && touched.current)) setCite(ans.citations.valid[0] ?? null);
  }, []);

  // One orchestrated moment on arrival: the first example answers itself and its lines get marked.
  useEffect(() => {
    const first = sorted[0];
    const ex = first?.examples[0];
    if (!first || !ex) return;
    const t = setTimeout(() => {
      if (!touched.current) choose(first.id, ex, true);
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!repo) return null;
  const k = q ? `${repo.id}|${q}` : "";
  const state = k ? answers[k] : undefined;
  const answer = state && state !== "loading" && !("error" in state) ? state : null;

  return (
    <div className="card p-3 sm:p-5 lg:p-6">
      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Choose a project">
        {sorted.map((r) => (
          <button
            key={r.id}
            role="tab"
            aria-selected={r.id === repo.id}
            onClick={() => {
              touched.current = true;
              setRepoId(r.id);
              setQ(null);
              setCite(null);
            }}
            className={`press inline-flex min-h-11 items-center gap-2 rounded-full border px-4 text-sm ${
              r.id === repo.id ? "border-ink bg-ink text-bg" : "border-line-strong text-ink hover:border-ink"
            }`}
          >
            <span className="font-mono">{r.name.split("/")[1]}</span>
            <span className={r.id === repo.id ? "opacity-75" : "text-muted"}>{level(r.chunks)}</span>
          </button>
        ))}
      </div>
      <p className="mt-3 max-w-[70ch] text-muted">{repo.description}</p>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-6">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-muted" id="stage-q-label">
            Click a question
          </p>
          <ul className="mt-2 flex flex-col gap-1.5" aria-labelledby="stage-q-label">
            {repo.examples.map((ex) => (
              <li key={ex}>
                <button
                  onClick={() => choose(repo.id, ex)}
                  aria-pressed={q === ex}
                  className={`press w-full rounded-md border px-3.5 py-2.5 text-left font-serif text-[1.05rem] leading-snug ${
                    q === ex ? "border-primary bg-surface-2 text-ink" : "border-transparent text-link hover:border-line hover:bg-surface-2"
                  }`}
                >
                  {ex}
                </button>
              </li>
            ))}
          </ul>
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (typed.trim().length >= 3 && !liveOff) choose(repo.id, typed.trim());
            }}
          >
            <label className="sr-only" htmlFor="stage-q">
              Ask your own question about {repo.name}
            </label>
            <input
              id="stage-q"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              disabled={liveOff}
              maxLength={1000}
              autoComplete="off"
              placeholder={liveOff ? "Live questions are paused right now" : "Or type your own question"}
              className="min-h-11 min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-3 text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-primary/20 disabled:bg-surface-2"
            />
            <Button type="submit" disabled={liveOff || typed.trim().length < 3 || state === "loading"}>
              Ask
            </Button>
          </form>
          <div className="mt-4 min-h-[6rem]" aria-live="polite">
            {state === "loading" && (
              <div role="status" aria-label="Reading the code">
                <p className="text-sm text-muted">Reading the code…</p>
                <div className="mt-3 space-y-2.5" aria-hidden>
                  <div className="skeleton h-3.5 w-[92%]" />
                  <div className="skeleton h-3.5 w-[78%]" />
                  <div className="skeleton h-3.5 w-[60%]" />
                </div>
              </div>
            )}
            {state && state !== "loading" && "error" in state && (
              <p role="alert" className="text-alert">
                {state.error}
              </p>
            )}
            {answer && (
              <div key={k} className="rise">
                <AnswerView payload={answer} active={cite} onOpen={(c) => setCite(c)} />
              </div>
            )}
            {!q && <p className="text-muted">The answer shows up here, with tags you can click.</p>}
          </div>
        </div>
        <div className="lg:sticky lg:top-24 lg:self-start lg:h-[26rem]">
          <CodeWindow repo={repo.id} cite={cite} />
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <p className="t-small max-w-[58ch] text-muted">
          {liveOff ? "The example answers are saved from a test run. Live questions are paused right now." : "The example answers are saved from a test run. Questions you type are answered live."}
        </p>
        <Button variant="secondary" onClick={() => onOpenFull(repo.name)}>
          Open {repo.name.split("/")[1]} in the full app <Arrow size={18} />
        </Button>
      </div>
    </div>
  );
}
