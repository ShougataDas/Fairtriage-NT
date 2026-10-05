"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { CircleCheck, Scale, SlidersHorizontal } from "lucide-react";
import { fetcher, post, type ThresholdScenario, type TripThreshold } from "@/lib/api";
import { cx, when } from "@/lib/format";
import { Button, Card, CardTitle, ErrorBox, Pill, Spinner, inputClass } from "@/components/ui";
import { moneyRange } from "@/components/TripCost";

const days = (n: number | null) => (n == null ? "—" : `${n} day${n === 1 ? "" : "s"}`);

/**
 * The equity lever, made a visible human decision. How long remote routine
 * work waits for a trip is set by one number; this shows what each value
 * means for remote tenants, against Darwin, and what it costs in trips, and
 * lets a coordinator choose it with a reason that is recorded.
 */
export function TripPolicy() {
  const { data, error, isLoading, mutate } = useSWR<TripThreshold>("/api/policy/trip-threshold", fetcher);
  const [pick, setPick] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    if (data && pick == null) setPick(data.setting.value);
  }, [data, pick]);

  if (isLoading) return <Spinner label="Working out the options" />;
  if (error) return <ErrorBox error={error} onRetry={() => mutate()} />;
  if (!data || pick == null) return null;

  const rows = data.scenarios;
  const cur = rows.find((r) => r.current) ?? rows[0];
  const sel = rows.reduce((a, b) => (Math.abs(b.multiple - pick) < Math.abs(a.multiple - pick) ? b : a), rows[0]);
  const idx = rows.indexOf(sel);
  const changed = sel.multiple !== cur.multiple;
  const noWork = cur.wait_max_days == null;

  async function apply() {
    setBusy(true);
    setSaveError(null);
    try {
      await mutate(post<TripThreshold>("/api/policy/trip-threshold", { multiple: sel.multiple, reason: reason.trim() }), {
        revalidate: false,
      });
      setSaved(`Trip threshold set to ${sel.multiple}×. Remote routine waits and the trip planner use it from now.`);
      setReason("");
    } catch (e) {
      setSaveError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle icon={<Scale className="size-5 text-ink" aria-hidden />}>Trip policy: you decide the remote wait</CardTitle>
      <p className="-mt-2 mb-4 max-w-3xl text-muted">
        Fixing the town first is always cheaper. Remote routine repairs wait for a maintenance trip, and a community gets one when
        its oldest routine job has waited a set multiple of its {data.target_days}-day target. Fewer trips save money; remote tenants
        pay for it in time. FairTriage shows both sides. The choice, and the reason for it, belong to a person.
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <span className="font-bold">In force now:</span>
        <Pill tone="ink">{data.setting.value}× target</Pill>
        {data.setting.source === "coordinator" ? (
          <span className="text-muted">
            set by {data.setting.actor} {data.setting.at ? when(data.setting.at) : ""}: “{data.setting.reason}”
          </span>
        ) : (
          <span className="text-muted">from the policy file</span>
        )}
      </div>

      {noWork ? (
        <p className="rounded-xl bg-canvas p-4 text-muted">No remote routine work is waiting, so there is nothing to compare yet.</p>
      ) : (
        <>
          <label htmlFor="threshold" className="flex items-center gap-2 font-bold">
            <SlidersHorizontal className="size-4" aria-hidden /> What if the threshold were <span className="text-ink">{sel.multiple}×</span>?
          </label>
          <input
            id="threshold"
            type="range"
            min={0}
            max={rows.length - 1}
            step={1}
            value={idx}
            onChange={(e) => {
              setPick(rows[Number(e.target.value)].multiple);
              setSaved(null);
            }}
            className="mt-2 w-full accent-ink"
            aria-valuetext={`${sel.multiple} times the target`}
          />
          <div className="mb-5 flex justify-between text-xs text-muted" aria-hidden>
            {rows.map((r) => (
              <span key={r.multiple} className={cx(r.current && "font-bold text-ink")}>{r.multiple}×</span>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Figure label="Remote routine wait" value={`up to ${days(sel.wait_max_days)}`} sub={`about ${days(sel.wait_avg_days)} on average`}
              delta={changed ? (sel.wait_max_days ?? 0) - (cur.wait_max_days ?? 0) : 0} unit="days" lowerIsBetter />
            <Figure label="Against Darwin" value={sel.ratio_vs_darwin ? `${sel.ratio_vs_darwin}× as long` : "—"}
              sub={`Darwin routine: about ${days(data.darwin_routine_days)}`} />
            <Figure label="Planned trips" value={`${sel.trips_per_month} a month`} sub="for remote routine work"
              delta={changed ? Math.round((sel.trips_per_month - cur.trips_per_month) * 10) / 10 : 0} unit="trips" />
            <Figure label="Trip cost" value={moneyRange(sel.cost_month_low, sel.cost_month_high)} sub="a month, estimated"
              money={changed ? [sel.cost_month_low - cur.cost_month_low, sel.cost_month_high - cur.cost_month_high] : undefined} />
          </div>

          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="py-2 pr-3">Threshold</th>
                  <th scope="col" className="py-2 pr-3">Remote wait, up to</th>
                  <th scope="col" className="py-2 pr-3">On average</th>
                  <th scope="col" className="py-2 pr-3">× Darwin</th>
                  <th scope="col" className="py-2 pr-3">Trips a month</th>
                  <th scope="col" className="py-2">Trip cost a month</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((r) => (
                  <tr
                    key={r.multiple}
                    onClick={() => {
                      setPick(r.multiple);
                      setSaved(null);
                    }}
                    className={cx("cursor-pointer", r === sel && "bg-ink-soft", "hover:bg-canvas")}
                  >
                    <td className="py-2 pr-3 font-bold">
                      {r.multiple}× {r.current && <Pill tone="ink">now</Pill>}
                    </td>
                    <td className="py-2 pr-3 tabular-nums">{days(r.wait_max_days)}</td>
                    <td className="py-2 pr-3 tabular-nums">{days(r.wait_avg_days)}</td>
                    <td className="py-2 pr-3 tabular-nums">{r.ratio_vs_darwin ?? "—"}×</td>
                    <td className="py-2 pr-3 tabular-nums">{r.trips_per_month}</td>
                    <td className="py-2 tabular-nums">{moneyRange(r.cost_month_low, r.cost_month_high)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="mt-5 flex flex-col gap-2 border-t border-line pt-4">
        {saved ? (
          <p role="status" className="flex items-center gap-2 font-bold text-routine">
            <CircleCheck className="size-5" aria-hidden /> {saved}
          </p>
        ) : (
          <>
            <label htmlFor="threshold-reason" className="font-bold">
              {changed ? `Use ${sel.multiple}× from now` : "Move the slider to choose a different setting"}{" "}
              <span className="font-normal text-muted">· your reason is recorded with your name</span>
            </label>
            <textarea
              id="threshold-reason"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={400}
              disabled={!changed}
              placeholder="For example: budget approved for more trips this quarter, to cut remote waits"
              className={inputClass}
            />
            <Button onClick={apply} busy={busy} disabled={!changed || reason.trim().length < 10} className="self-start">
              Set threshold to {sel.multiple}×
            </Button>
          </>
        )}
        {saveError != null && <ErrorBox error={saveError} />}
      </div>

      <details className="mt-4 text-sm text-muted">
        <summary className="cursor-pointer font-bold">How these figures are worked out</summary>
        <ul className="mt-2 list-disc pl-5">
          {data.assumptions.map((a) => <li key={a}>{a}</li>)}
          <li>Based on {data.remote_routine_open} remote routine jobs waiting in {data.communities} communities now.</li>
        </ul>
      </details>

      {data.history.length > 0 && (
        <div className="mt-4">
          <p className="font-bold">Changes to this setting</p>
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {data.history.map((h) => (
              <li key={h.at}>
                {when(h.at)}: {h.from}× → <strong>{h.to}×</strong> by {h.actor} · <span className="italic">“{h.reason}”</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function Figure({
  label, value, sub, delta, unit, lowerIsBetter, money,
}: {
  label: string; value: string; sub: string; delta?: number; unit?: string; lowerIsBetter?: boolean; money?: [number, number];
}) {
  const good = delta != null && delta !== 0 && (lowerIsBetter ? delta < 0 : false);
  return (
    <div className="rounded-xl bg-canvas p-3">
      <p className="text-xs font-bold uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-lg font-bold">{value}</p>
      <p className="text-sm text-muted">{sub}</p>
      {delta != null && delta !== 0 && (
        <p className={cx("text-sm font-bold", good ? "text-routine" : lowerIsBetter ? "text-immediate" : "text-graphite")}>
          {unit === "days"
            ? `${Math.abs(delta)} days ${delta < 0 ? "shorter" : "longer"} than now`
            : `${Math.abs(delta)} ${delta > 0 ? "more" : "fewer"} a month than now`}
        </p>
      )}
      {money && (money[0] !== 0 || money[1] !== 0) && (
        <p className="text-sm font-bold text-graphite">
          {moneyRange(Math.abs(money[0]), Math.abs(money[1]))} {money[1] > 0 ? "more" : "less"} a month than now
        </p>
      )}
    </div>
  );
}
