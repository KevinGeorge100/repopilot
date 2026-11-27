"use client";
import { Arrow } from "@/components/ui/Icons";
import { Button } from "@/components/ui/Button";

type Props = {
  id: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: (v: string) => void;
  error: string | null;
  note?: string;
  busy?: boolean;
};

/** The primary call to action: paste a link, get a repo you can question. */
export function RepoForm({ id, value, onChange, onSubmit, error, note, busy }: Props) {
  return (
    <div>
      <form
        className="flex flex-col gap-3 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(value);
        }}
      >
        <label className="sr-only" htmlFor={id}>
          Public GitHub repository link
        </label>
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="github.com/owner/repo"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          inputMode="url"
          aria-invalid={error ? true : undefined}
          aria-describedby={`${id}-help`}
          className="min-h-12 min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-4 font-mono text-[0.95rem] text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-primary/20"
        />
        <Button type="submit" size="lg" loading={busy} className="sm:w-auto">
          Ask about this repo <Arrow size={18} />
        </Button>
      </form>
      <p id={`${id}-help`} className="t-small mt-2 text-muted">
        {error ? (
          <span role="alert" className="text-alert">
            {error}
          </span>
        ) : (
          note
        )}
      </p>
    </div>
  );
}
