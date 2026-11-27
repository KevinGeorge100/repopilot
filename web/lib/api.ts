import type { AnswerPayload, Config, RepoStatus } from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fail(r: Response): Promise<never> {
  let msg = `Request failed (${r.status})`;
  try {
    const j = await r.json();
    if (typeof j.detail === "string") msg = j.detail;
    else if (Array.isArray(j.detail)) msg = "Check the input and try again.";
  } catch {}
  throw new Error(msg);
}

export async function getConfig(): Promise<Config | null> {
  try {
    const r = await fetch(`${API}/api/config`);
    return r.ok ? r.json() : null;
  } catch {
    return null; // an older or unreachable API: fall back to the plain "paste a repo" screen
  }
}

export async function startIndex(url: string): Promise<RepoStatus> {
  const r = await fetch(`${API}/api/repos`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  return r.ok ? r.json() : fail(r);
}

export async function getRepo(id: string): Promise<RepoStatus> {
  const r = await fetch(`${API}/api/repos/${encodeURIComponent(id)}`);
  return r.ok ? r.json() : fail(r);
}

export type FileWindow = { path: string; start: number; end: number; total: number; lines: string[] };

export async function getLines(id: string, path: string, start: number, end: number): Promise<FileWindow> {
  const q = new URLSearchParams({ path, start: String(start), end: String(end) });
  const r = await fetch(`${API}/api/repos/${encodeURIComponent(id)}/file?${q}`);
  return r.ok ? r.json() : fail(r);
}

export type AskHandlers = {
  onToolCall: (name: string, input: Record<string, unknown>) => void;
  onToolResult: (name: string, error: boolean) => void;
  onRepair: () => void;
  onAnswer: (a: AnswerPayload) => void;
  onError: (message: string) => void;
};

/** POST + stream: EventSource can't POST, so parse the SSE frames by hand. */
export async function ask(repo: string, question: string, h: AskHandlers, signal?: AbortSignal): Promise<void> {
  const r = await fetch(`${API}/api/ask`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ repo, question }),
    signal,
  });
  if (!r.ok || !r.body) return fail(r);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const ev = /^event: (.+)$/m.exec(frame)?.[1];
      const raw = /^data: (.+)$/m.exec(frame)?.[1];
      if (!ev || !raw) continue;
      const d = JSON.parse(raw);
      if (ev === "tool_call") h.onToolCall(d.name, d.input);
      else if (ev === "tool_result") h.onToolResult(d.name, d.error);
      else if (ev === "repair") h.onRepair();
      else if (ev === "answer") h.onAnswer(d);
      else if (ev === "error") h.onError(d.message);
    }
  }
}
