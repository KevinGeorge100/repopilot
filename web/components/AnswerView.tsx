"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AnswerPayload, Citation } from "@/lib/types";
import { citeKey } from "@/lib/types";

const CITE = /^([\w][\w./-]*\.[A-Za-z]\w*):(\d+)(?:-(\d+))?$/;

export function parseCite(text: string): Citation | null {
  const m = CITE.exec(text.trim());
  if (!m) return null;
  const start = Number(m[2]);
  return { path: m[1], start, end: Number(m[3] ?? m[2]) };
}

type Props = {
  payload: AnswerPayload;
  active: Citation | null;
  onOpen: (c: Citation) => void;
};

export function AnswerView({ payload, active, onOpen }: Props) {
  const { citations: rep } = payload;
  const good = new Set(rep.valid.map(citeKey));
  const unread = new Set(rep.ungrounded);
  const activeKey = active ? citeKey(active) : null;

  return (
    <div>
      <div className="prose-answer">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code({ children, className }) {
              const text = String(children).replace(/\n$/, "");
              const c = !className && !text.includes("\n") ? parseCite(text) : null;
              if (!c) return <code className={className}>{children}</code>;
              const key = citeKey(c);
              const bad = !good.has(key) || unread.has(key);
              return (
                <button
                  type="button"
                  className="cite"
                  data-status={bad ? "bad" : "ok"}
                  data-active={activeKey === key}
                  disabled={!good.has(key)}
                  onClick={() => onOpen(c)}
                  title={bad ? "This citation could not be verified" : "Show these lines"}
                >
                  {c.path.split("/").slice(-2).join("/")}:{c.start}
                  {c.end !== c.start ? `–${c.end}` : ""}
                </button>
              );
            },
          }}
        >
          {payload.answer}
        </ReactMarkdown>
      </div>
      <Verification payload={payload} />
    </div>
  );
}

function Verification({ payload }: { payload: AnswerPayload }) {
  const { citations: c, stopped, steps, usage } = payload;
  const total = c.valid.length + c.invalid.length;
  const problems = c.invalid.length + c.ungrounded.length;
  const k = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
  return (
    <div className="mt-4 flex flex-col gap-1.5 text-sm text-graphite" role="status">
      {total === 0 && c.abstained ? (
        <p>The agent searched and found nothing matching in this repo, so there is no code to cite.</p>
      ) : total === 0 ? (
        <p className="text-alert">This answer cites no code, so treat it with caution.</p>
      ) : problems === 0 ? (
        <p className="flex items-center gap-2">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden className="shrink-0 text-cobalt">
            <path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>
            All {total} {total === 1 ? "citation was" : "citations were"} found in the repo and read by the agent.
          </span>
        </p>
      ) : (
        <div className="text-alert">
          <p>
            {problems} of {total + c.ungrounded.length} {problems === 1 ? "citation" : "citations"} could not be verified. They are struck through above.
          </p>
          <ul className="mt-1 list-disc pl-5 text-graphite">
            {c.invalid.map((i) => (
              <li key={i.citation}>
                <code className="font-mono text-xs">{i.citation}</code>: {i.reason}
              </li>
            ))}
            {c.ungrounded.map((u) => (
              <li key={u}>
                <code className="font-mono text-xs">{u}</code>: exists, but the agent never read it
              </li>
            ))}
          </ul>
        </div>
      )}
      {stopped !== "done" && (
        <p className="text-alert">
          {stopped === "max_steps" ? "The agent ran out of steps before finishing." : "The agent hit its token budget before finishing."} Try a narrower question.
        </p>
      )}
      <p>
        {steps} {steps === 1 ? "step" : "steps"}, {k(usage.input_tokens + usage.output_tokens)} tokens
      </p>
    </div>
  );
}
