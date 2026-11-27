"use client";
import { useEffect, useState } from "react";

const STEPS = [
  {
    n: "1",
    title: "Pick a repo and a question",
    body: "Open one of the ready-made repos and click an example, or type your own question about the code.",
  },
  {
    n: "2",
    title: "Read the cited answer",
    body: "Each claim ends in a small tag like signer.py:94-96, the file and line numbers it comes from.",
  },
  {
    n: "3",
    title: "Click a tag, see the lines",
    body: "The exact lines light up in the real source on the right, so you can check the answer yourself.",
  },
];

const SAMPLE = [
  { n: 94, t: "    :param digest_method: Hash function to use when generating the HMAC" },
  { n: 95, t: "        signature. Defaults to :attr:`default_digest_method`, which" },
  { n: 96, t: "        defaults to :func:`hashlib.sha1`. Note that the security of the" },
];

/** A static, honest picture of what an answer looks like (real lines from the indexed itsdangerous repo). */
function Sample() {
  return (
    <figure className="mt-8 rounded-md border border-rule bg-sheet p-4 sm:p-5" aria-label="Example of a cited answer">
      <figcaption className="text-sm font-semibold text-graphite">What you get back</figcaption>
      <p className="mt-3 font-serif text-lg leading-relaxed">
        <span className="font-sans text-sm text-graphite">Q: </span>Which hash does Signer use by default?
      </p>
      <p className="mt-2 font-serif text-lg leading-relaxed">
        <span className="font-sans text-sm text-graphite">A: </span>SHA-1, through <code>hashlib.sha1</code>{" "}
        <span className="cite" aria-hidden="true">
          signer.py:94-96
        </span>
      </p>
      <p className="mt-4 text-sm text-graphite">Clicking the tag shows the source, with those lines marked:</p>
      <pre className="mt-2 overflow-x-auto rounded border border-rule bg-paper py-2 font-mono text-xs leading-6">
        {SAMPLE.map((l) => (
          <div key={l.n} className="flex whitespace-pre bg-marker/70">
            <span className="w-10 shrink-0 select-none pr-3 text-right text-graphite">{l.n}</span>
            <span>{l.t}</span>
          </div>
        ))}
      </pre>
    </figure>
  );
}

export function HowItWorks() {
  return (
    <section className="mt-16" aria-labelledby="how">
      <h2 id="how" className="text-2xl font-bold tracking-tight">
        How it works
      </h2>
      <ol className="mt-5 grid gap-6 sm:grid-cols-3">
        {STEPS.map((s) => (
          <li key={s.n}>
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-ink font-mono text-sm text-sheet">
              {s.n}
            </span>
            <h3 className="mt-2 font-semibold">{s.title}</h3>
            <p className="mt-1 text-graphite">{s.body}</p>
          </li>
        ))}
      </ol>
      <Sample />
      <p className="mt-4 max-w-[62ch] text-graphite">
        Before showing an answer, RepoPilot checks every tag: the file exists, the lines are inside it, and the
        AI really read them. A tag that fails is struck through and explained, never hidden.
      </p>
    </section>
  );
}

const FAQ = [
  {
    q: "What is this good for?",
    a: "Getting oriented in unfamiliar code fast: where something happens, how a feature works, why a function exists. Every answer points at the lines, so you spend time reading code, not guessing.",
  },
  {
    q: "Why only three repos?",
    a: "This free hosted copy has limited memory, so it comes with three small open-source repos already indexed (itsdangerous, click and slugify). To use any public repo, run RepoPilot yourself: the README has three commands.",
  },
  {
    q: "What are the example questions?",
    a: "Real answers saved from an evaluation run, labelled as such, so they load instantly. Anything you type yourself is answered live by the model.",
  },
  {
    q: "Can I trust the answers?",
    a: "Check them: that is the point of the citations. On a 38-question test over these repos, 35 passed. The failures and the limits of that test are written up in the evaluation results.",
  },
  {
    q: "Is my data kept?",
    a: "RepoPilot’s server does not save your questions. The code around your question is sent to an AI provider to write a live answer, so do not point this at private code.",
  },
];

export function Faq() {
  return (
    <section className="mt-14" aria-labelledby="faq">
      <h2 id="faq" className="text-2xl font-bold tracking-tight">
        Good to know
      </h2>
      <div className="mt-4 divide-y divide-rule border-y border-rule">
        {FAQ.map((f) => (
          <details key={f.q} className="group py-3">
            <summary className="cursor-pointer list-none font-semibold marker:content-none">
              <span className="mr-2 inline-block text-cobalt-ink transition group-open:rotate-90">›</span>
              {f.q}
            </summary>
            <p className="mt-2 max-w-[62ch] pl-5 text-graphite">{f.a}</p>
          </details>
        ))}
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
    <aside className="mb-6 max-w-[68ch] rounded-md border border-rule bg-sheet px-4 py-3 text-sm" aria-label="How to read an answer">
      <p className="font-semibold">How to read an answer</p>
      <ul className="mt-1.5 list-disc space-y-1 pl-5 text-graphite">
        <li>
          Tags like <span className="cite">file.py:10-20</span> are the evidence. Click one to see those lines
          highlighted on the right.
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
        className="mt-2 text-cobalt-ink underline underline-offset-4"
      >
        Got it, hide this
      </button>
    </aside>
  );
}
