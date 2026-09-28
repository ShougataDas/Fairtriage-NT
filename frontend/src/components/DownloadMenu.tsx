"use client";

import { useState } from "react";
import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { cx } from "@/lib/format";

/** Download requests as CSV or Excel, using the filters on screen. */
export function DownloadMenu({ tier, remote, q }: { tier: string; remote: boolean; q: string }) {
  const [scope, setScope] = useState<"queue" | "all">("queue");

  const href = (format: "csv" | "xlsx") => {
    const p = new URLSearchParams({ format, scope });
    if (tier) p.set("tier", tier);
    if (remote) p.set("remote", "true");
    if (q.trim()) p.set("q", q.trim());
    return `/api/export?${p}`;
  };
  const filtered = Boolean(tier || remote || q.trim());

  return (
    <section aria-labelledby="dl-title" className="flex flex-col gap-3 rounded-2xl border border-line bg-paper p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-ink-soft text-ink"><Download className="size-5" aria-hidden /></span>
        <div>
          <h2 id="dl-title" className="font-bold">Download requests</h2>
          <p className="text-sm text-muted">
            {scope === "queue"
              ? filtered ? "The queue as filtered below, in ranked order." : "The whole ranked queue, in order."
              : filtered ? "Every request matching the filters below, whatever its status." : "Every request, whatever its status."}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="What to download" className="flex rounded-xl border border-line p-1">
          {(["queue", "all"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              aria-pressed={scope === s}
              className={cx("rounded-lg px-3 py-1.5 text-sm font-bold", scope === s ? "bg-ink text-white" : "text-muted hover:text-graphite")}
            >
              {s === "queue" ? "Queue" : "All requests"}
            </button>
          ))}
        </div>
        <a href={href("xlsx")} download className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-ink px-4 py-2 font-bold text-white hover:bg-ink-strong">
          <FileSpreadsheet className="size-4" aria-hidden /> Excel (.xlsx)
        </a>
        <a href={href("csv")} download className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-line bg-paper px-4 py-2 font-bold text-ink hover:bg-ink-soft">
          <FileText className="size-4" aria-hidden /> CSV
        </a>
      </div>
    </section>
  );
}
