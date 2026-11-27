import type { Config } from "@/lib/types";
import { Faq, HowItWorks } from "@/components/Guide";

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
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-4 py-16 sm:px-6">
      <p className="mb-10 text-xl font-bold tracking-tight">RepoPilot</p>
      <h1 className="max-w-[18ch] text-4xl font-bold leading-[1.08] tracking-tight sm:text-6xl">
        Ask a repo anything. See the lines behind every answer.
      </h1>
      <p className="mt-5 max-w-[52ch] font-serif text-xl leading-relaxed text-graphite">
        RepoPilot reads the code, answers your question, and checks that every citation points to real lines it
        actually read. Click a citation to see those lines highlighted in the source.
      </p>

      {repos.length > 0 && (
        <section className="mt-10" aria-label="Repositories ready to explore">
          <h2 className="text-lg font-semibold tracking-tight">Start with a repo that is already indexed</h2>
          <ul className="mt-3 divide-y divide-rule border-y border-rule">
            {repos.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => onOpen(r.name)}
                  className="group flex w-full flex-col gap-0.5 px-1 py-3.5 text-left transition hover:bg-sheet sm:flex-row sm:items-baseline sm:gap-6"
                >
                  <span className="font-mono text-sm font-medium text-cobalt-ink underline decoration-rule underline-offset-4 group-hover:decoration-cobalt sm:w-56 sm:shrink-0">
                    {r.name}
                  </span>
                  <span className="text-graphite">
                    {r.description}{" "}
                    <span className="text-sm">
                      {r.chunks.toLocaleString()} pieces of code
                      {r.examples.length > 0 ? `, ${r.examples.length} example questions` : ""}.
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {canIndex ? (
        <>
          <form
            className="mt-9 flex flex-col gap-3 sm:flex-row"
            onSubmit={(e) => {
              e.preventDefault();
              onOpen(input);
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
            <button type="submit" className="rounded-md bg-ink px-6 py-3 font-semibold text-sheet transition hover:bg-cobalt-ink">
              Open repo
            </button>
          </form>
          {formError && (
            <p role="alert" className="mt-3 text-alert">
              {formError}
            </p>
          )}
        </>
      ) : (
        <p className="mt-8 max-w-[58ch] text-graphite">
          This hosted demo answers questions about the repositories above so it can respond instantly. To index any
          public repo, run RepoPilot yourself: the{" "}
          <a href={SOURCE_URL} className="text-cobalt-ink underline underline-offset-4">
            README
          </a>{" "}
          has the three commands.
        </p>
      )}
      {!canIndex && formError && (
        <p role="alert" className="mt-3 text-alert">
          {formError}
        </p>
      )}

      <HowItWorks />
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
