"use client";

import useSWR from "swr";
import { fetcher, type Equity } from "@/lib/api";
import { TIERS, cx, tierStyle } from "@/lib/format";
import { Card, CardTitle, ErrorBox, PageHeader, Spinner } from "@/components/ui";

export default function FairnessPage() {
  const { data: m, error, isLoading, mutate } = useSWR<Equity>("/api/metrics/equity", fetcher, { refreshInterval: 30000 });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Fairness" lede="Numbers computed from the live queue, not claims about it." />
      {isLoading && <Spinner />}
      {error && <ErrorBox error={error} onRetry={() => mutate()} />}
      {m && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Metric
              title="Rank ignores location"
              value={m.rank_location_invariance.pct != null ? `${m.rank_location_invariance.pct}%` : "n/a"}
              good={m.rank_location_invariance.pct === 100}
              body={`${m.rank_location_invariance.identical} of ${m.rank_location_invariance.checked} jobs have exactly the rank they would have with location removed. Must be 100%.`}
            />
            <Metric
              title="Remote jobs on someone else's trip"
              value={m.remote_jobs_scheduled.passenger_share_pct != null ? `${m.remote_jobs_scheduled.passenger_share_pct}%` : "n/a"}
              body={`${m.remote_jobs_scheduled.as_passengers} rode along, ${m.remote_jobs_scheduled.on_own_trip} had their own trip. A high share means remote work depends on other people's emergencies.`}
            />
            <Metric
              title="Passed over twice or more"
              value={`${m.deferrals.remote?.at_or_above_2 ?? 0} remote · ${m.deferrals.urban?.at_or_above_2 ?? 0} urban`}
              body="Rank cannot fall after a report is made, so repeated deferral is how slow neglect would show up."
            />
          </div>

          <Card>
            <CardTitle>Expected wait: remote against urban</CardTitle>
            <p className="-mt-2 mb-5 text-muted">Same tier, same rank rules. The difference is travel, roads and crew numbers.</p>
            <div className="flex flex-col gap-6">
              {TIERS.map((tier) => {
                const g = m.wait_gap_by_tier[tier];
                if (!g) return null;
                const max = Math.max(g.remote_days ?? 0, g.urban_days ?? 0, 0.1);
                return (
                  <div key={tier}>
                    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                      <span className={cx("font-bold", tierStyle[tier].text)}>{tier}</span>
                      <span className="text-sm text-muted">
                        {g.ratio ? `remote waits ${g.ratio}× as long` : ""} · {g.n_remote} remote / {g.n_urban} urban jobs
                      </span>
                    </div>
                    <Bar label="Remote" value={g.remote_days} max={max} strong />
                    <Bar label="Urban" value={g.urban_days} max={max} />
                  </div>
                );
              })}
            </div>
          </Card>
          <p className="text-sm text-muted">Crew numbers per region are placeholders and distances are estimates, so treat the wait figures as illustrative until real capacity data is supplied.</p>
        </>
      )}
    </div>
  );
}

function Metric({ title, value, body, good }: { title: string; value: string; body: string; good?: boolean }) {
  return (
    <Card>
      <h2 className="font-bold text-muted">{title}</h2>
      <p className={cx("mt-2 text-4xl font-bold", good && "text-routine")}>{value}</p>
      <p className="mt-2 text-muted">{body}</p>
    </Card>
  );
}

function Bar({ label, value, max, strong }: { label: string; value: number | null; max: number; strong?: boolean }) {
  return (
    <div className="mb-1.5 flex items-center gap-3 text-sm">
      <span className="w-16 text-muted">{label}</span>
      <div className="h-6 flex-1 overflow-hidden rounded-lg bg-canvas">
        <div className={cx("h-full rounded-lg", strong ? "bg-ink" : "bg-ink/40")} style={{ width: `${((value ?? 0) / max) * 100}%` }} />
      </div>
      <span className="w-20 text-right font-bold tabular-nums">{value != null ? `${value} days` : "—"}</span>
    </div>
  );
}
