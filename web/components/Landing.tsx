import type { Config } from "@/lib/types";
import { Faq, HowItWorks } from "@/components/Guide";
import { ProofCard } from "@/components/ProofCard";
import { RepoForm } from "@/components/RepoForm";
import { SiteHeader, SOURCE_URL } from "@/components/SiteHeader";
import { Stage } from "@/components/Stage";
import { UseCases } from "@/components/UseCases";
import { Check, Gift, Shield } from "@/components/ui/Icons";
import { LinkButton } from "@/components/ui/Button";

export { SOURCE_URL };

type Props = {
  config: Config | null;
  input: string;
  setInput: (v: string) => void;
  formError: string | null;
  onOpen: (raw: string) => void;
};

const TRUST = [
  { Icon: Shield, text: "Every citation is checked against the real code" },
  { Icon: Check, text: "35 of 38 test questions answered correctly" },
  { Icon: Gift, text: "Free, no sign-up" },
];

export function Landing({ config, input, setInput, formError, onOpen }: Props) {
  const repos = config?.repos ?? [];
  const canIndex = config ? config.indexing : true;
  const liveOff = config !== null && (!config.live_questions || config.daily_remaining === 0);
  const note = `Ready to ask in a few seconds. Very large repos are trimmed to their ${(config?.max_chunks ?? 2500).toLocaleString()} most relevant pieces of code.`;

  return (
    <>
      <SiteHeader />
      <main id="main">
        <section className="aurora">
          <div className="shell grid grid-cols-1 gap-10 pb-14 pt-10 sm:pt-14 lg:grid-cols-12 lg:items-center lg:gap-12 lg:pb-20 lg:pt-20">
            <div className="lg:col-span-7">
              <h1 className="t-display rise max-w-[16ch]">Ask questions about code. Check the answers.</h1>
              <p className="t-lead rise mt-5 max-w-[52ch]" style={{ "--d": 1 } as React.CSSProperties}>
                Opening someone else’s project is confusing: where is anything? RepoPilot answers in plain English and marks the exact lines of code it used, so you can see for yourself that it’s right.
              </p>
              <div className="rise mt-8 max-w-[40rem]" style={{ "--d": 2 } as React.CSSProperties}>
                {canIndex ? (
                  <RepoForm id="repo" value={input} onChange={setInput} onSubmit={onOpen} error={formError} note={note} />
                ) : (
                  <>
                    <LinkButton href="#try" variant="primary" size="lg">
                      Try an example
                    </LinkButton>
                    <p className="t-small mt-3 max-w-[56ch] text-muted">
                      This copy answers questions about the ready-made projects below so it can respond instantly. To use any public repo, run RepoPilot yourself: the{" "}
                      <a href={SOURCE_URL} className="text-link underline underline-offset-4">
                        README
                      </a>{" "}
                      has the commands.
                    </p>
                    {formError && (
                      <p role="alert" className="mt-2 text-alert">
                        {formError}
                      </p>
                    )}
                  </>
                )}
                {canIndex && repos.length > 0 && (
                  <p className="t-small mt-4 text-muted">
                    No repo in mind?{" "}
                    <a href="#try" className="font-semibold text-link underline underline-offset-4">
                      Start with a tiny one
                    </a>
                    .
                  </p>
                )}
              </div>
              <ul className="rise mt-8 grid gap-3 sm:grid-cols-3 lg:max-w-[40rem]" style={{ "--d": 3 } as React.CSSProperties}>
                {TRUST.map(({ Icon, text }) => (
                  <li key={text} className="flex items-start gap-2.5 text-[0.92rem] text-muted">
                    <Icon size={20} className="mt-0.5 shrink-0 text-verified" />
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="lg:col-span-5">
              <ProofCard />
            </div>
          </div>
        </section>

        {repos.length > 0 && (
          <section id="try" className="shell scroll-mt-20 pb-6 pt-4 sm:pt-10" aria-labelledby="try-h">
            <h2 id="try-h" className="t-h2">
              Try it now
            </h2>
            <p className="t-lead mt-3 max-w-[56ch]">Nothing to install. Pick a project, click a question, then click a tag in the answer.</p>
            <div className="mt-8">
              <Stage repos={repos} liveOff={liveOff} onOpenFull={onOpen} />
            </div>
          </section>
        )}

        <UseCases />
        <HowItWorks />
        <Faq />

        {canIndex && (
          <section className="shell pb-16" aria-labelledby="cta-h">
            <div className="card aurora p-6 sm:p-10">
              <h2 id="cta-h" className="t-h2 max-w-[22ch]">
                Got a project you’re curious about?
              </h2>
              <div className="mt-6 max-w-[40rem]">
                <RepoForm id="repo-2" value={input} onChange={setInput} onSubmit={onOpen} error={formError} note={note} />
              </div>
            </div>
          </section>
        )}
      </main>

      <footer className="border-t border-line">
        <div className="shell flex flex-col gap-4 py-8 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-[60ch]">Code snippets are sent to an AI provider to write each live answer, so don’t point this at anything private.</p>
          <nav aria-label="Project links" className="flex flex-wrap gap-x-5 gap-y-1">
            <a className="inline-flex min-h-11 items-center underline underline-offset-4 hover:text-ink" href={SOURCE_URL}>
              Source code
            </a>
            <a className="inline-flex min-h-11 items-center underline underline-offset-4 hover:text-ink" href={`${SOURCE_URL}/blob/main/evals/RESULTS.md`}>
              Evaluation results
            </a>
            <a className="inline-flex min-h-11 items-center underline underline-offset-4 hover:text-ink" href="/styleguide/">
              Design system
            </a>
          </nav>
        </div>
      </footer>
    </>
  );
}
