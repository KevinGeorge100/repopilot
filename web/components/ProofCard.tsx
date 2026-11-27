import { Check } from "@/components/ui/Icons";

const CHECKS = ["The file exists", "Those lines exist", "The AI read them"];

/** A static, real example (itsdangerous) of what "a checked answer" means. The ticks draw in once on load. */
export function ProofCard() {
  return (
    <figure className="card rise p-5 sm:p-6" style={{ "--d": 3 } as React.CSSProperties} aria-label="Example of a checked answer">
      <figcaption className="t-small text-muted">A real answer, from the itsdangerous project</figcaption>
      <p className="mt-4 text-sm font-semibold text-muted">Question</p>
      <p className="font-serif text-lg leading-snug">Which hash does Signer use by default?</p>
      <p className="mt-4 text-sm font-semibold text-muted">Answer</p>
      <p className="font-serif text-lg leading-relaxed">
        SHA-1, through <code className="rounded bg-surface-2 px-1 font-mono text-[0.85em]">hashlib.sha1</code>{" "}
        <span className="cite" data-active="true" aria-hidden="true">
          signer.py:94-96
        </span>
      </p>
      <ul className="mt-5 space-y-2 border-t border-line pt-4" aria-label="Checks that passed">
        {CHECKS.map((c, i) => (
          <li key={c} className="flex items-center gap-2.5 text-[0.95rem]">
            <span className="pop inline-flex h-6 w-6 items-center justify-center rounded-full bg-verified/15 text-verified" style={{ animationDelay: `${600 + i * 260}ms` }}>
              <Check size={14} style={{ animationDelay: `${700 + i * 260}ms` }} />
            </span>
            {c}
          </li>
        ))}
      </ul>
    </figure>
  );
}
