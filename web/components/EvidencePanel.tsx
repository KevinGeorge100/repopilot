"use client";
import { useEffect, useRef, useState } from "react";
import { getLines, type FileWindow } from "@/lib/api";
import type { Citation } from "@/lib/types";
import { citeKey } from "@/lib/types";

const CONTEXT = 14;

type Props = {
  repo: string;
  sources: Citation[];
  active: Citation | null;
  onSelect: (c: Citation) => void;
  onClose: () => void;
};

export function EvidencePanel({ repo, sources, active, onSelect, onClose }: Props) {
  const [win, setWin] = useState<FileWindow | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const hitRef = useRef<HTMLDivElement | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const key = active ? citeKey(active) : null;

  useEffect(() => {
    if (!active) return;
    let live = true;
    getLines(repo, active.path, Math.max(1, active.start - CONTEXT), active.end + CONTEXT)
      .then((w) => {
        if (live) {
          setWin(w);
          setErr(null);
        }
      })
      .catch((e: Error) => live && (setErr(e.message), setWin(null)));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo, key]);

  useEffect(() => {
    const box = boxRef.current;
    if (box && hitRef.current) box.scrollTop = Math.max(0, hitRef.current.offsetTop - box.clientHeight / 3);
  }, [win]);

  if (!active) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-graphite">
        <p className="max-w-[26ch]">Select a citation in an answer to see the exact lines, highlighted in the source.</p>
      </div>
    );
  }

  let firstHit = true;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-start justify-between gap-3 border-b border-rule px-4 py-3">
        <div className="min-w-0">
          <p className="truncate font-mono text-sm font-medium" title={active.path}>
            {active.path}
          </p>
          <p className="text-sm text-graphite">
            Lines {active.start}
            {active.end !== active.start ? `–${active.end}` : ""}
            {win ? ` of ${win.total}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded px-2 py-1 text-sm text-graphite hover:bg-rule lg:hidden"
        >
          Close
        </button>
      </div>

      {sources.length > 1 && (
        <div className="flex gap-1 overflow-x-auto border-b border-rule px-3 py-2" role="tablist" aria-label="Sources in this answer">
          {sources.map((s) => (
            <button
              key={citeKey(s)}
              type="button"
              role="tab"
              aria-selected={citeKey(s) === key}
              onClick={() => onSelect(s)}
              className={`shrink-0 rounded px-2 py-1 font-mono text-xs ${
                citeKey(s) === key ? "bg-ink text-sheet" : "text-graphite hover:bg-rule"
              }`}
            >
              {s.path.split("/").pop()}:{s.start}
            </button>
          ))}
        </div>
      )}

      <div ref={boxRef} tabIndex={0} role="region" aria-label={`Source code: ${active.path}`} className="relative min-h-0 flex-1 overflow-auto bg-night py-3 font-mono text-[0.8rem] leading-6">
        {err && <p className="px-4 font-sans text-code-ink">Couldn’t load this file: {err}</p>}
        {!err && !win && <p className="px-4 font-sans text-code-ink">Loading lines…</p>}
        {win?.lines.map((line, idx) => {
          const n = win.start + idx;
          const hit = n >= active.start && n <= active.end;
          const ref = hit && firstHit ? ((firstHit = false), hitRef) : undefined;
          return (
            <div key={n} ref={ref} className="code-line" data-hit={hit}>
              <span className="gutter">{n}</span>
              <span>{line || " "}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
