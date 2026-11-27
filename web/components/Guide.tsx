"use client";
import { useEffect, useState } from "react";
import { Check } from "@/components/ui/Icons";

const STEPS = [
  { n: "1", title: "Pick a project and a question", body: "Open a ready-made project and click an example, or paste your own GitHub link and type a question." },
  { n: "2", title: "Read the cited answer", body: "Each claim ends in a small tag like signer.py:94-96: the file and the line numbers it came from." },
  { n: "3", title: "Click a tag, see the lines", body: "The exact lines light up in the real source, so you can check the answer yourself." },
];

export function HowItWorks() {
  return (
    <section id="how" className="section" aria-labelledby="how-h">
      <div className="shell">
        <h2 id="how-h" className="t-h2 max-w-[22ch]">
          How it works
        </h2>
        <ol className="mt-8 grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <li key={s.n} className="card p-5 sm:p-6">
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-marker font-mono text-sm font-semibold text-on-marker">{s.n}</span>
              <h3 className="t-h3 mt-4">{s.title}</h3>
              <p className="mt-2 text-muted">{s.body}</p>
            </li>
          ))}
        </ol>
        <p className="mt-6 flex max-w-[70ch] items-start gap-2 text-muted">
          <Check className="mt-1 shrink-0 text-verified" size={18} />
          <span>Before an answer is shown, RepoPilot checks every tag: the file exists, the lines are inside it, and the AI really read them. A tag that fails is struck through and explained, never hidden.</span>
        </p>
      </div>
    </section>
  );
}

const FAQ = [
  { q: "What is this good for?", a: "Getting oriented in unfamiliar code fast: where something happens, how a feature works, why a function exists. Every answer points at the lines, so you spend your time reading code, not guessing." },
  { q: "Can I use any repo?", a: "Any public GitHub repo. Paste the link and you can ask in a few seconds while search sharpens in the background. Very large repos are trimmed to their most relevant code, and this free hosted copy keeps only the last few repos people added." },
  { q: "What are the example answers?", a: "Real answers saved from a test run, labelled as such, so they load instantly. Anything you type yourself is answered live by the model." },
  { q: "Can I trust the answers?", a: "Check them: that is the point of the tags. On a 38-question test over three projects, 35 were right. I wrote those questions myself, and the failures are written up in the evaluation results." },
  { q: "Is my data kept?", a: "RepoPilot’s server does not save your questions. The code around your question is sent to an AI provider to write a live answer, so do not point this at private code." },
];

export function Faq() {
  return (
    <section id="faq" className="section" aria-labelledby="faq-h">
      <div className="shell max-w-3xl">
        <h2 id="faq-h" className="t-h2">
          Good to know
        </h2>
        <div className="mt-6 divide-y divide-line border-y border-line">
          {FAQ.map((f) => (
            <details key={f.q} className="group py-1">
              <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 rounded-md py-2 font-semibold marker:content-none hover:text-link">
                <span aria-hidden className="inline-block text-link transition-transform duration-200 group-open:rotate-90">›</span>
                {f.q}
              </summary>
              <p className="max-w-[64ch] pb-3 pl-6 text-muted">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

const KEY = "repopilot.tips.dismissed";

/** A short, dismissible reminder shown above the first answer. Works without localStorage. */
export function ReadingTips({ forceOpen, onDismiss }: { forceOpen: boolean; onDismiss: () => void }) {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    try {
      setHidden(localStorage.getItem(KEY) === "1");
    } catch {
      /* storage blocked: just show the tips */
    }
  }, []);
  if (hidden && !forceOpen) return null;
  return (
    <aside className="card rise mb-6 max-w-[68ch] px-4 py-3 text-sm" aria-label="How to read an answer">
      <p className="font-semibold">How to read an answer</p>
      <ul className="mt-1.5 list-disc space-y-1 pl-5 text-muted">
        <li>
          Tags like <span className="cite">file.py:10-20</span> are the evidence. Click one to see those lines highlighted.
        </li>
        <li>The steps above an answer show what the AI searched and read before it answered.</li>
        <li>A struck-through tag means the check failed. Don’t rely on that claim.</li>
      </ul>
      <button
        type="button"
        onClick={() => {
          setHidden(true);
          onDismiss();
          try {
            localStorage.setItem(KEY, "1");
          } catch {
            /* ignore */
          }
        }}
        className="press mt-2 inline-flex min-h-11 items-center text-link underline underline-offset-4"
      >
        Got it, hide this
      </button>
    </aside>
  );
}
