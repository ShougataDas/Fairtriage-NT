"use client";

import { ChevronDown, Fuel, HardHat, Package, Receipt, Truck } from "lucide-react";
import type { TripCost as Cost } from "@/lib/api";
import { cx } from "@/lib/format";

const money = (n: number) => `$${n.toLocaleString("en-AU")}`;
export const moneyRange = (lo: number, hi: number) => (lo === hi ? money(lo) : `${money(lo)} – ${money(hi)}`);

const ICON: Record<string, React.ReactNode> = {
  transport: <Fuel className="size-5" aria-hidden />,
  logistics: <Truck className="size-5" aria-hidden />,
  labour: <HardHat className="size-5" aria-hidden />,
  other: <Package className="size-5" aria-hidden />,
};

/**
 * The probable cost of a recommended trip. Each group opens to show every line
 * and how it was worked out, so nothing is hidden inside the total. Shown to
 * help plan and budget; it never changes who is served first.
 */
export function TripCost({ cost }: { cost: Cost }) {
  const a = cost.assumptions;
  const range = (x: [number, number], unit: string) => (x[0] === x[1] ? `${x[0]} ${unit}` : `${x[0]} to ${x[1]} ${unit}`);
  return (
    <section aria-label="Probable trip cost" className="rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 font-bold">
            <Receipt className="size-5 text-ink" aria-hidden /> Probable trip cost
          </p>
          <p className="mt-1 text-3xl font-bold tracking-tight">{moneyRange(cost.low, cost.high)}</p>
          <p className="text-sm text-muted">Whole trip, AUD, GST excluded. An estimate for planning, not a quote.</p>
        </div>
        {cost.separate && cost.saving && (
          <div className="rounded-xl bg-routine-soft p-3 text-right">
            <p className="text-xs font-bold uppercase tracking-wide text-muted">{cost.separate.trips} separate trips</p>
            <p className="font-bold">{moneyRange(cost.separate.low, cost.separate.high)}</p>
            {cost.saving.high > 0 && (
              <p className="text-sm font-bold text-routine">this trip saves about {moneyRange(cost.saving.low, cost.saving.high)}</p>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 2xl:grid-cols-4">
        {cost.groups.map((g) => (
          <div key={g.key} className="rounded-xl bg-canvas p-3">
            <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-muted">
              {ICON[g.key]} {g.label}
            </p>
            <p className="mt-1 font-bold">{moneyRange(g.low, g.high)}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-col gap-2">
        {cost.groups.map((g) => (
          <details key={g.key} className="group rounded-xl border border-line">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 font-bold">
              <span className="flex items-center gap-2">{ICON[g.key]} {g.label}</span>
              <span className="flex items-center gap-2">
                {moneyRange(g.low, g.high)}
                <ChevronDown className="size-4 transition group-open:rotate-180" aria-hidden />
              </span>
            </summary>
            <ul className="divide-y divide-line border-t border-line">
              {g.lines.map((l) => (
                <li key={l.label} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 px-4 py-2">
                  <span className="min-w-0 flex-1">
                    <span className="font-bold">{l.label}</span>
                    <span className="block text-sm text-muted">{l.basis}</span>
                  </span>
                  <span className={cx("font-mono text-sm", l.high === 0 && "text-muted")}>{moneyRange(l.low, l.high)}</span>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>

      <p className="mt-4 text-sm text-muted">
        Based on {a.vehicle ? `a ${a.vehicle}` : ""}
        {a.vehicle && a.aircraft ? " and " : ""}
        {a.aircraft ? `a ${a.aircraft}` : ""}; {a.people} {a.people === 1 ? "person" : "people"};{" "}
        {range(a.days, a.days[1] === 1 ? "day" : "days")}
        {a.nights[1] > 0 ? `, ${range(a.nights, a.nights[1] === 1 ? "night" : "nights")} away` : ""};{" "}
        {a.travel_hours} h travel and {range(a.onsite_hours, "h")} on site for {a.jobs} job{a.jobs > 1 ? "s" : ""}.
        {cost.placeholder_rates && " Rates are placeholders until the department's contract rates are entered."}
      </p>
      <p className="mt-1 text-sm font-bold text-graphite">
        Cost is shown to help plan and budget. It never changes which tenants are served first.
      </p>
    </section>
  );
}
