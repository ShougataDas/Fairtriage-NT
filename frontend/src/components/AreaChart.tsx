"use client";

import { useMemo, useRef, useState } from "react";
import { BarChart3, Table2, X } from "lucide-react";
import type { QueueRow } from "@/lib/api";
import { TIERS, cx } from "@/lib/format";

// Chart fills for the three priorities. Same meaning as the badges, but
// stepped apart in lightness so they stay distinct with colour blindness:
// validated (scripts/validate_palette.js) at CVD dE >= 8 against white.
// Amber is below 3:1 against white, so every bar also carries its numbers as
// text, and a table view is one click away.
const FILL: Record<string, string> = { Immediate: "#b3261e", Urgent: "#d98b16", Routine: "#2f8a5f" };
const AREA_ORDER = ["Darwin", "Palmerston", "Darwin rural", "Top End", "Big Rivers", "Arnhem"];

type AreaStat = {
  area: string;
  counts: Record<string, number>;
  total: number;
  past: number;
  pastByTier: Record<string, number>;
  avgDays: number;
  remote: boolean;
};

/** Open repairs by area and priority. Click an area to filter the queue. */
export function AreaChart({ rows, area, onArea }: { rows: QueueRow[]; area: string; onArea: (a: string) => void }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const box = useRef<HTMLDivElement>(null);

  const stats = useMemo<AreaStat[]>(() => {
    const by = new Map<string, AreaStat>();
    for (const r of rows) {
      const a = r.area || "Other";
      const s = by.get(a) ?? {
        area: a, counts: { Immediate: 0, Urgent: 0, Routine: 0 }, total: 0, past: 0,
        pastByTier: { Immediate: 0, Urgent: 0, Routine: 0 }, avgDays: 0, remote: false,
      };
      s.counts[r.tier] = (s.counts[r.tier] ?? 0) + 1;
      s.total += 1;
      s.avgDays += r.days_open;
      s.remote ||= r.remote;
      if (r.past_target) {
        s.past += 1;
        s.pastByTier[r.tier] = (s.pastByTier[r.tier] ?? 0) + 1;
      }
      by.set(a, s);
    }
    const order = (a: string) => (AREA_ORDER.indexOf(a) === -1 ? 99 : AREA_ORDER.indexOf(a));
    return [...by.values()]
      .map((s) => ({ ...s, avgDays: s.total ? s.avgDays / s.total : 0 }))
      .sort((a, b) => order(a.area) - order(b.area));
  }, [rows]);

  const max = Math.max(1, ...stats.map((s) => s.total));
  const busiest = stats.reduce<AreaStat | null>((b, s) => (!b || s.total > b.total ? s : b), null);
  const mostLate = stats.reduce<AreaStat | null>((b, s) => (!b || s.past / s.total > b.past / b.total ? s : b), null);

  function move(e: React.MouseEvent, text: string) {
    const r = box.current?.getBoundingClientRect();
    if (r) setTip({ x: e.clientX - r.left, y: e.clientY - r.top, text });
  }

  return (
    <section aria-labelledby="area-title" className="rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6">
      <div className="mb-1 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="area-title" className="flex items-center gap-2 text-lg font-bold">
            <BarChart3 className="size-5 text-ink" aria-hidden /> Open repairs by area
          </h2>
          <p className="text-sm text-muted">
            {busiest && `${busiest.area} has the most open repairs (${busiest.total}). `}
            {mostLate && mostLate.past > 0 && `${mostLate.area} has the largest share past target (${Math.round((100 * mostLate.past) / mostLate.total)}%). `}
            Click an area to show only its repairs.
          </p>
        </div>
        <div role="group" aria-label="Show as" className="flex rounded-xl border border-line p-1">
          {(["chart", "table"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={cx("flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-bold", view === v ? "bg-ink text-white" : "text-muted hover:text-graphite")}
            >
              {v === "chart" ? <BarChart3 className="size-4" aria-hidden /> : <Table2 className="size-4" aria-hidden />}
              {v === "chart" ? "Chart" : "Table"}
            </button>
          ))}
        </div>
      </div>

      {area && (
        <button onClick={() => onArea("")} className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-ink-soft px-3 py-1 text-sm font-bold text-ink">
          Showing {area} only <X className="size-3.5" aria-hidden /> <span className="sr-only">Clear area filter</span>
        </button>
      )}

      {/* legend: always shown, so priority is never told by colour alone */}
      <ul className="mb-3 mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm" aria-label="Legend">
        {TIERS.map((t) => (
          <li key={t} className="flex items-center gap-2 text-graphite">
            <span className="inline-block size-3 rounded-[3px]" style={{ background: FILL[t] }} aria-hidden /> {t}
          </li>
        ))}
        <li className="text-muted">Numbers: open repairs · late (past target)</li>
      </ul>

      {stats.length === 0 && <p className="py-6 text-center text-muted">No open repairs.</p>}

      {view === "chart" && stats.length > 0 && (
        <div ref={box} className="relative" onMouseLeave={() => setTip(null)}>
          <ul className="flex flex-col gap-1">
            {stats.map((s) => {
              const active = area === s.area;
              const dim = area && !active;
              const label = `${s.area}: ${s.total} open repairs, ${TIERS.map((t) => `${s.counts[t]} ${t}`).join(", ")}, ${s.past} past target`;
              return (
                <li key={s.area}>
                  <button
                    onClick={() => onArea(active ? "" : s.area)}
                    aria-pressed={active}
                    aria-label={`${label}. ${active ? "Showing only this area; click to show all." : "Click to show only this area."}`}
                    className={cx(
                      "grid w-full grid-cols-[7.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-2 py-1.5 text-left transition sm:grid-cols-[9rem_minmax(0,1fr)_9rem]",
                      active ? "bg-ink-soft" : "hover:bg-canvas",
                      dim && "opacity-45",
                    )}
                  >
                    <span className="truncate text-sm font-bold text-graphite">
                      {s.area}
                      {s.remote && <span className="ml-1 font-normal text-muted">· remote</span>}
                    </span>
                    <span className="flex h-6 items-center" aria-hidden>
                      <span className="flex h-full gap-[2px]" style={{ width: `${(s.total / max) * 100}%` }}>
                        {TIERS.filter((t) => s.counts[t] > 0).map((t, i, arr) => (
                          <span
                            key={t}
                            className={cx("h-full min-w-[3px]", i === arr.length - 1 && "rounded-r-[4px]")}
                            style={{ background: FILL[t], flexGrow: s.counts[t], flexBasis: 0 }}
                            onMouseMove={(e) =>
                              move(e, `${s.area} · ${t}: ${s.counts[t]} repair${s.counts[t] > 1 ? "s" : ""}${s.pastByTier[t] ? `, ${s.pastByTier[t]} past target` : ""}`)
                            }
                          />
                        ))}
                      </span>
                    </span>
                    <span className="whitespace-nowrap text-sm tabular-nums">
                      <strong className="text-graphite">{s.total}</strong>
                      {s.past > 0 && <span className="text-muted"> · {s.past} late</span>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          {tip && (
            <div
              role="tooltip"
              className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg bg-graphite px-3 py-1.5 text-sm font-bold text-white shadow-lg"
              style={{ left: tip.x, top: tip.y - 10 }}
            >
              {tip.text}
            </div>
          )}
        </div>
      )}

      {view === "table" && stats.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-2 pr-3">Area</th>
                {TIERS.map((t) => <th key={t} className="pr-3 text-right">{t}</th>)}
                <th className="pr-3 text-right">Total</th>
                <th className="pr-3 text-right">Past target</th>
                <th className="text-right">Avg days waiting</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line tabular-nums">
              {stats.map((s) => (
                <tr key={s.area} onClick={() => onArea(area === s.area ? "" : s.area)} className={cx("cursor-pointer hover:bg-canvas", area === s.area && "bg-ink-soft")}>
                  <td className="py-2 pr-3 font-bold">{s.area}</td>
                  {TIERS.map((t) => <td key={t} className="pr-3 text-right">{s.counts[t]}</td>)}
                  <td className="pr-3 text-right font-bold">{s.total}</td>
                  <td className="pr-3 text-right">{s.past}</td>
                  <td className="text-right">{s.avgDays.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
