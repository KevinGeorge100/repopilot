import type { Config } from "@/lib/types";
import { Faq, HowItWorks } from "@/components/Guide";
import { Stage } from "@/components/Stage";

export const SOURCE_URL = "https://github.com/KevinGeorge100/repopilot";

type Props = {
  config: Config | null;
  input: string;
  setInput: (v: string) => void;
  formError: string | null;
  onOpen: (raw: string) => void;
};

export function Landing({ config, input, setInput, formError, onOpen }: Props) {
  const repos = config?.repos ?? [];
  const canIndex = config ? config.indexing : true;
  const liveOff = config !== null && (!config.live_questions || config.daily_remaining === 0);
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-4 py-10 sm:px-6">
      <p className="mb-6 text-xl font-bold tracking-tight">RepoPilot</p>
      <h1 className="max-w-[20ch] text-4xl font-bold leading-[1.06] tracking-tight sm:text-5xl">
        Ask questions about code. Check the answers.
      </h1>
      <p className="mt-4 max-w-[56ch] font-serif text-lg sm:text-xl leading-relaxed text-graphite">
        Opening someone else’s project is confusing: where is anything? RepoPilot answers in plain English and
        marks the exact lines of code it used, so you can see for yourself that it’s right.
      </p>

      {canIndex ? (
        <div className="mt-8 max-w-[44rem]">
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={(e) => {
              e.preventDefault();
              onOpen(input);
            }}
          >
            <label className="sr-only" htmlFor="repo">
              Public GitHub repository
            </label>
            <input
              id="repo"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Paste a public GitHub link"
              autoComplete="off"
              spellCheck={false}
              className="min-w-0 flex-1 rounded-md border border-rule bg-sheet px-4 py-3 font-mono text-sm outline-none focus:border-cobalt"
            />
            <button type="submit" className="rounded-md bg-ink px-6 py-3 font-semibold text-sheet transition hover:bg-cobalt-ink">
              Ask about this repo
            </button>
          </form>
          <p className="mt-2 text-sm text-graphite">
            Ready to ask in a few seconds. Very large repos are trimmed to their{" "}
            {(config?.max_chunks ?? 2500).toLocaleString()} most relevant pieces of code. Or try one of the ready-made
            projects below.
          </p>
          {formError && (
            <p role="alert" className="mt-3 text-alert">
              {formError}
            </p>
          )}
        </div>
      ) : (
        <p className="mt-8 max-w-[58ch] text-graphite">
          This hosted demo answers questions about the repositories below so it can respond instantly. To index any
          public repo, run RepoPilot yourself: the{" "}
          <a href={SOURCE_URL} className="text-cobalt-ink underline underline-offset-4">
            README
          </a>{" "}
          has the three commands.
        </p>
      )}

      {repos.length > 0 && <Stage repos={repos} liveOff={liveOff} onOpenFull={onOpen} />}

      {repos.length > 0 && (
        <section className="mt-14" aria-labelledby="who">
          <h2 id="who" className="text-2xl font-bold tracking-tight">
            Who it helps
          </h2>
          <ul className="mt-4 grid gap-5 sm:grid-cols-3">
            <li>
              <p className="font-semibold">You’re learning</p>
              <p className="mt-1 text-graphite">Read real open-source projects and ask “why is it written this way?” when you’re stuck.</p>
            </li>
            <li>
              <p className="font-semibold">You’re new on a team</p>
              <p className="mt-1 text-graphite">Find where a feature lives in minutes instead of asking a teammate or searching for an hour.</p>
            </li>
            <li>
              <p className="font-semibold">You’re reviewing a change</p>
              <p className="mt-1 text-graphite">Get an explanation of what a pull request does, with the changed lines pointed out.</p>
            </li>
          </ul>
        </section>
      )}

      {!canIndex && formError && (
        <p role="alert" className="mt-3 text-alert">
          {formError}
        </p>
      )}

      <HowItWorks showSample={repos.length === 0} />
      <Faq />

      <p className="mt-16 max-w-[62ch] text-sm text-graphite">
        Code snippets are sent to an AI provider to write each live answer, so don’t point this at anything private.{" "}
        <a href={SOURCE_URL} className="text-cobalt-ink underline underline-offset-4">
          Source code and evaluation results on GitHub
        </a>
        .
      </p>
    </main>
  );
}
