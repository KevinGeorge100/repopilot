import type { Step } from "@/lib/types";

function label(s: Step): string {
  const i = s.input as Record<string, string | number | undefined>;
  if (s.name === "search_code") return `Searched for “${i.query ?? ""}”`;
  if (s.name === "read_file") {
    const range = i.start_line ? `, lines ${i.start_line}${i.end_line ? `–${i.end_line}` : "+"}` : "";
    return `Read ${i.path ?? "a file"}${range}`;
  }
  if (s.name === "list_tree") return `Listed ${i.path && i.path !== "." ? i.path : "the repo root"}`;
  return s.name;
}

export function Trail({ steps, working, repairing }: { steps: Step[]; working: boolean; repairing: boolean }) {
  if (steps.length === 0 && !working) return null;
  return (
    <ol className="relative my-3 ml-1 border-l border-rule pl-4 text-sm text-graphite" aria-label="What the agent did">
      {steps.map((s, idx) => (
        <li key={idx} className="step-in relative py-0.5">
          <span
            aria-hidden
            className={`absolute -left-[1.3rem] top-[0.75em] h-1.5 w-1.5 rounded-full ${
              s.failed ? "bg-alert" : s.done ? "bg-cobalt" : "bg-rule"
            }`}
          />
          <span className={s.failed ? "text-alert" : undefined}>{label(s)}</span>
          {s.failed && <span className="text-alert"> (failed)</span>}
        </li>
      ))}
      {repairing && <li className="step-in py-0.5 text-alert">Checking citations again, one was wrong</li>}
      {working && (
        <li className="relative py-0.5 italic">
          <span aria-hidden className="absolute -left-[1.3rem] top-[0.75em] h-1.5 w-1.5 animate-pulse rounded-full bg-cobalt" />
          {steps.length === 0 ? "Starting" : "Thinking"}
        </li>
      )}
    </ol>
  );
}
