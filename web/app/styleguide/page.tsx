import type { Metadata } from "next";
import { Button, LinkButton } from "@/components/ui/Button";
import { Check, Logo } from "@/components/ui/Icons";
import { SiteHeader } from "@/components/SiteHeader";
import { ProofCard } from "@/components/ProofCard";

export const metadata: Metadata = { title: "Design system · RepoPilot" };

const COLORS: [string, string, string][] = [
  ["bg", "Page background", "bg-bg"],
  ["surface", "Cards and inputs", "bg-surface"],
  ["surface-2", "Tinted panels, code chips", "bg-surface-2"],
  ["ink", "Primary text", "bg-ink"],
  ["muted", "Secondary text", "bg-muted"],
  ["line", "Dividers", "bg-line"],
  ["line-strong", "Input borders (3:1)", "bg-line-strong"],
  ["primary", "Main actions", "bg-primary"],
  ["link", "Links and tags", "bg-link"],
  ["marker", "The highlighter: evidence only", "bg-marker"],
  ["verified", "Checks that passed", "bg-verified"],
  ["alert", "Errors, failed checks", "bg-alert"],
  ["night", "Code window", "bg-night"],
];

const TYPE: [string, string, string][] = [
  ["Display", "t-display", "Ask questions about code"],
  ["Heading 2", "t-h2", "How it works"],
  ["Heading 3", "t-h3", "Pick a project and a question"],
  ["Lead (serif)", "t-lead", "Answers and intros are set in a serif for reading."],
  ["Body", "", "Interface text is 16px on a 1.6 line height, under 70 characters wide."],
  ["Small", "t-small", "Helper text, captions and counts."],
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="py-8">
      <h2 className="t-h3 mb-4 border-b border-line pb-2">{title}</h2>
      {children}
    </section>
  );
}

export default function StyleGuide() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="shell py-10">
        <h1 className="t-h2">Design system</h1>
        <p className="t-lead mt-3 max-w-[60ch]">The tokens and components behind RepoPilot. Toggle the theme in the header: every colour below is a token with a light and a dark value, and each text pair is checked against WCAG 2.2 AA in CI.</p>

        <Section title="Colour">
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {COLORS.map(([name, use, cls]) => (
              <li key={name} className="card overflow-hidden">
                <div className={`h-14 ${cls}`} />
                <div className="p-3">
                  <p className="font-mono text-sm font-semibold">{name}</p>
                  <p className="t-small text-muted">{use}</p>
                </div>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Type: Schibsted Grotesk for interface, Newsreader for reading, JetBrains Mono for code">
          <div className="space-y-5">
            {TYPE.map(([label, cls, sample]) => (
              <div key={label} className="grid gap-1 sm:grid-cols-[9rem_1fr] sm:gap-6">
                <p className="t-small text-muted">{label}</p>
                <p className={cls}>{sample}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Buttons: 44px minimum height, press feedback, loading state">
          <div className="flex flex-wrap items-center gap-3">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button loading>Loading</Button>
            <Button disabled>Disabled</Button>
            <LinkButton href="#main" variant="secondary">
              Link button
            </LinkButton>
          </div>
        </Section>

        <Section title="Citation tags: the link between words and evidence">
          <p className="prose-answer">
            Valid <button className="cite">signer.py:94-96</button> active <button className="cite" data-active="true">signer.py:94-96</button> failed{" "}
            <button className="cite" data-status="bad" disabled>
              signer.py:900
            </button>
          </p>
        </Section>

        <Section title="Code window and the highlighter sweep">
          <div className="max-w-xl overflow-hidden rounded-lg bg-night py-2 font-mono text-[0.8rem] leading-6">
            {([
              [92, "    or hmac. Defaults to :attr:`default_key_derivation`, which"],
              [93, "    defaults to ``django-concat``."],
              [94, "    :param digest_method: Hash function to use when generating the HMAC"],
              [95, "        signature. Defaults to :attr:`default_digest_method`, which"],
              [96, "        defaults to :func:`hashlib.sha1`."],
            ] as [number, string][]).map(([n, t], i) => (
              <div key={n} className="code-line" data-hit={n >= 94} style={{ "--i": Math.max(0, i - 2) } as React.CSSProperties}>
                <span className="gutter">{n}</span>
                <span>{t}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Feedback: skeleton, verified tick, card">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="card space-y-2.5 p-5" role="status" aria-label="Loading example">
              <div className="skeleton h-3.5 w-[92%]" />
              <div className="skeleton h-3.5 w-[78%]" />
              <div className="skeleton h-3.5 w-[60%]" />
            </div>
            <div className="card flex items-center gap-3 p-5">
              <span className="pop inline-flex h-8 w-8 items-center justify-center rounded-full bg-verified/15 text-verified">
                <Check size={18} />
              </span>
              <p>All 3 citations were found in the repo and read by the agent.</p>
            </div>
          </div>
          <div className="mt-4 max-w-md">
            <ProofCard />
          </div>
        </Section>

        <Section title="Rules">
          <ul className="list-disc space-y-1.5 pl-5 text-muted">
            <li>Spacing is a 4px grid; sections use one fluid step. Content lives in one 84rem container with fluid gutters.</li>
            <li>Breakpoints: 640 (phone landscape), 768 (tablet), 1024 (laptop: two columns appear), 1280 (wide: side rail).</li>
            <li>Yellow is reserved for evidence (the highlighter) and step numbers. Green only ever means a check passed. Meaning is never colour alone: ticks and strike-through carry it too.</li>
            <li>Touch targets are at least 44px. Focus is a 3px ring. Motion answers an action, apart from one entrance and the highlighter sweep, and all of it stops under reduced-motion.</li>
            <li className="flex items-center gap-2"><Logo size={20} /> The mark is a line of code with the highlighter on it.</li>
          </ul>
        </Section>
      </main>
    </>
  );
}
