export type Citation = { path: string; start: number; end: number };

export type RepoStatus = {
  id: string;
  url: string;
  status: "queued" | "cloning" | "chunking" | "embedding" | "ready" | "error";
  done: number;
  total: number;
  chunks: number;
  truncated: boolean;
  error: string | null;
};

export type AnswerPayload = {
  answer: string;
  stopped: "done" | "max_steps" | "budget";
  steps: number;
  usage: { input_tokens: number; output_tokens: number; cache_read_tokens: number };
  citations: {
    valid: Citation[];
    invalid: { citation: string; reason: string }[];
    ungrounded: string[];
    validity: number;
    ok: boolean;
    abstained?: boolean;
  };
  /** Set when the answer is a stored result from an evaluation run rather than generated just now. */
  cached?: boolean;
  source?: { run?: string; model?: string | null; provider?: string | null };
};

export type DemoRepo = { id: string; name: string; description: string; chunks: number; examples: string[] };

export type Config = {
  demo: boolean;
  indexing: boolean;
  live_questions: boolean;
  daily_remaining: number;
  indexing_remaining?: number;
  max_chunks?: number | null;
  repos: DemoRepo[];
};

export type Step = { name: string; input: Record<string, unknown>; done: boolean; failed: boolean };

export type Turn = {
  id: number;
  question: string;
  steps: Step[];
  repairing: boolean;
  status: "working" | "done" | "error";
  answer?: AnswerPayload;
  error?: string;
};

export const citeKey = (c: Citation) => `${c.path}:${c.start}-${c.end}`;
