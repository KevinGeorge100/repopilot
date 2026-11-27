import { Carousel } from "@/components/ui/Carousel";

/** Decorative: a few lines of code with the highlighter on one of them. */
function MiniCode({ hit }: { hit: number }) {
  const widths = [64, 82, 48, 74, 56];
  return (
    <div className="rounded-md bg-night p-3" aria-hidden>
      {widths.map((w, i) => (
        <div key={i} className={`my-1 h-2.5 rounded-sm ${i === hit ? "bg-marker" : "bg-code-muted/40"}`} style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}

const CASES = [
  { title: "You’re learning to code", body: "Read a real open-source project and ask why it’s written the way it is, without searching for an hour.", ask: "Why does this function return early?", hit: 1 },
  { title: "You’re new on a team", body: "Find where a feature lives without interrupting a teammate on your first week.", ask: "Where is the login handled?", hit: 3 },
  { title: "You’re reviewing a change", body: "Get what a pull request does and which added lines matter. Available from the command line and as an MCP tool for AI assistants.", ask: "What does this PR change?", hit: 2 },
  { title: "You’re checking an AI answer", body: "Every claim comes with the lines behind it, so you verify instead of trusting.", ask: "Show me where that happens.", hit: 0 },
  { title: "You’re teaching or onboarding", body: "Give students and new hires a guide that always points at the real code, not at stale docs.", ask: "How is this project organised?", hit: 4 },
];

export function UseCases() {
  return (
    <section id="uses" className="section overflow-hidden" aria-labelledby="uses-h">
      <div className="shell">
        <h2 id="uses-h" className="t-h2 max-w-[24ch]">
          Who it helps
        </h2>
        <p className="t-lead mt-3 max-w-[56ch]">If you’ve ever opened someone else’s project and not known where to start, this is for you.</p>
        <div className="mt-8">
          <Carousel
            label="Who RepoPilot helps"
            slides={CASES.map((c) => (
              <article key={c.title} className="card lift flex h-full flex-col gap-4 p-5 sm:p-6">
                <MiniCode hit={c.hit} />
                <h3 className="t-h3">{c.title}</h3>
                <p className="text-muted">{c.body}</p>
                <p className="mt-auto border-t border-line pt-3 font-serif text-[1.05rem] italic text-ink">Ask: “{c.ask}”</p>
              </article>
            ))}
          />
        </div>
      </div>
    </section>
  );
}
