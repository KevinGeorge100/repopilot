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
