"use client";

import { useState } from "react";

interface CreateTaskProps {
  disabled: boolean;
  onCreate: (title: string, description: string) => Promise<void>;
}

const SUGGESTIONS = [
  "Add authentication to Next.js project",
  "Deploy the app to production via Docker",
];

export default function CreateTaskForm({ disabled, onCreate }: CreateTaskProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate(title.trim(), description.trim());
      setTitle("");
      setDescription("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="rounded-xl border border-line bg-panel p-4"
    >
      <div className="mb-3">
        <label className="font-mono text-xs uppercase tracking-wider text-slate-400">
          Development Task
        </label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={disabled || busy}
          placeholder='e.g. "Add authentication to Next.js project"'
          className="mt-1 w-full rounded-lg border border-line bg-panel2 px-3 py-2.5 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none"
        />
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setTitle(s)}
            className="rounded-full border border-line px-2.5 py-1 text-[11px] text-slate-400 hover:border-accent hover:text-accent"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between gap-3">
        <button
          type="submit"
          disabled={disabled || busy || !title.trim()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-black transition hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Queuing…" : "Dispatch to ATLAS"}
        </button>
        {error && <span className="text-xs text-red-400">{error}</span>}
      </div>

      {disabled && (
        <p className="mt-2 text-[11px] text-amber">
          API offline — reconnect check in progress.
        </p>
      )}
    </form>
  );
}