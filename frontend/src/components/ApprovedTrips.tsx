"use client";

import { useState } from "react";
import Link from "next/link";
import { CircleCheck, CircleX, History, Plane, Truck, UserMinus } from "lucide-react";
import { post, type ConfirmedTrip } from "@/lib/api";
import { cx, hoursOrDays, when } from "@/lib/format";
import { Button, Empty, ErrorBox, Pill, TierBadge, inputClass } from "@/components/ui";

type Filter = "approved" | "completed" | "cancelled";
const LABEL: Record<Filter, string> = { approved: "Active", completed: "Completed", cancelled: "Cancelled" };
const ACTION: Record<string, string> = {
  approved: "Approved", cancelled: "Cancelled", completed: "Marked completed", job_removed: "Job removed",
};

/** Approved trips: see them by status, and change an approval. */
export function ApprovedTrips({ trips, onChanged }: { trips: ConfirmedTrip[]; onChanged: () => void }) {
  const [filter, setFilter] = useState<Filter>("approved");
  const counts = { approved: 0, completed: 0, cancelled: 0 } as Record<Filter, number>;
  for (const t of trips) counts[(t.status ?? "approved") as Filter]++;
  const shown = trips.filter((t) => (t.status ?? "approved") === filter);

  return (
    <section aria-label="Approved trips" className="flex flex-col gap-4">
      <div role="group" aria-label="Show trips" className="flex flex-wrap gap-2">
        {(["approved", "completed", "cancelled"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            aria-pressed={filter === f}
            className={cx(
              "rounded-xl border px-4 py-2 font-bold",
              filter === f ? "border-ink bg-ink text-white" : "border-line bg-paper text-muted hover:text-graphite",
            )}
          >
            {LABEL[f]} <span className={cx("ml-1 rounded-full px-2 text-sm", filter === f ? "bg-white/20" : "bg-canvas")}>{counts[f]}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 && (
        <Empty icon={<Truck className="size-8" aria-hidden />} title={`No ${LABEL[filter].toLowerCase()} trips`}>
          {filter === "approved" ? "Approve a recommended trip and it appears here, where you can change it." : null}
        </Empty>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {shown.map((t) => <TripCard key={t.id} trip={t} onChanged={onChanged} />)}
      </div>
    </section>
  );
}

function TripCard({ trip: t, onChanged }: { trip: ConfirmedTrip; onChanged: () => void }) {
  const [mode, setMode] = useState<null | "cancel" | { remove: string }>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const active = (t.status ?? "approved") === "approved";
  const jobs = t.jobs.filter((j) => !j.removed);
  const removed = t.jobs.filter((j) => j.removed);

  async function run(path: string, body: object) {
    setBusy(true);
    setError(null);
    try {
      await post(`/api/trips/${encodeURIComponent(t.id)}/${path}`, body);
      setMode(null);
      setReason("");
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={cx("flex flex-col gap-4 rounded-2xl border bg-paper p-5 shadow-sm", active ? "border-line" : "border-line/60 opacity-90")}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-bold leading-snug">{(t.headline ?? `${t.community}, ${t.trade}`).replace("Recommended trip: ", "")}</h3>
          <p className="text-sm text-muted">
            {t.trade} · approved {when(t.created_at)} · {jobs.length} job{jobs.length === 1 ? "" : "s"}
          </p>
        </div>
        <span className="flex gap-1">
          {t.route?.by_air && <Pill tone="ink"><Plane className="size-3" aria-hidden /> Charter</Pill>}
          <Pill tone={active ? "ink" : t.status === "completed" ? "good" : "bad"}>{LABEL[(t.status ?? "approved") as Filter]}</Pill>
        </span>
      </header>

      <ul className="flex flex-col divide-y divide-line">
        {jobs.map((j) => (
          <li key={j.request_id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
            <TierBadge tier={j.tier} size="sm" />
            <Link href={`/coordinator/requests/${j.request_id}`} className="font-mono text-ink hover:underline">{j.request_id}</Link>
            <span className="text-muted">{j.community}{j.address ? ` · ${j.address}` : ""}</span>
            <span className="ml-auto flex items-center gap-2">
              {j.eta_hours != null && active && <span className="text-muted">arrive {hoursOrDays(j.eta_hours)}</span>}
              {active && (
                <button
                  onClick={() => { setMode({ remove: j.request_id }); setReason(""); }}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1 font-bold text-immediate hover:bg-immediate-soft"
                  aria-label={`Remove ${j.request_id} from this trip`}
                >
                  <UserMinus className="size-4" aria-hidden /> Remove
                </button>
              )}
            </span>
          </li>
        ))}
        {removed.map((j) => (
          <li key={j.request_id} className="flex flex-wrap items-center gap-2 py-2 text-sm text-muted line-through decoration-1">
            <span className="font-mono">{j.request_id}</span> <span>{j.community}</span>
            <span className="ml-auto no-underline">removed</span>
          </li>
        ))}
      </ul>

      {active && mode && (
        <form
          className="flex flex-col gap-2 rounded-xl border-2 border-immediate/40 bg-immediate-soft/50 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (mode === "cancel") run("cancel", { reason });
            else run("remove", { request_id: mode.remove, reason });
          }}
        >
          <label htmlFor={`reason-${t.id}`} className="font-bold">
            {mode === "cancel"
              ? `Cancel this approval? All ${jobs.length} jobs go back to the queue.`
              : `Remove ${mode.remove} from this trip? It goes back to the queue.`}
          </label>
          <input
            id={`reason-${t.id}`}
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={400}
            placeholder="Reason (kept in the trip's history), e.g. crew vehicle broke down"
            className={inputClass}
          />
          {error != null && <ErrorBox error={error} />}
          <div className="flex gap-2">
            <Button type="submit" variant="danger" busy={busy} disabled={reason.trim().length < 3}>
              {mode === "cancel" ? "Cancel approval" : "Remove job"}
            </Button>
            <Button type="button" variant="secondary" onClick={() => setMode(null)}>Keep it</Button>
          </div>
        </form>
      )}

      {active && !mode && (
        <div className="flex flex-wrap gap-2 border-t border-line pt-3">
          <Button busy={busy} onClick={() => run("complete", {})}>
            <CircleCheck className="size-4" aria-hidden /> Mark completed
          </Button>
          <Button variant="secondary" onClick={() => { setMode("cancel"); setReason(""); }}>
            <CircleX className="size-4" aria-hidden /> Cancel approval
          </Button>
          {error != null && <ErrorBox error={error} />}
        </div>
      )}

      {t.history && t.history.length > 0 && (
        <details className="text-sm">
          <summary className="flex cursor-pointer items-center gap-1.5 font-bold text-muted"><History className="size-4" aria-hidden /> History ({t.history.length})</summary>
          <ol className="mt-2 flex flex-col gap-1 border-l-2 border-line pl-3">
            {t.history.map((h, i) => (
              <li key={i}>
                <strong>{ACTION[h.action] ?? h.action}</strong>
                {h.request_id ? ` ${h.request_id}` : ""} · {when(h.at)} · {h.actor}
                {h.reason && <span className="italic text-muted"> “{h.reason}”</span>}
              </li>
            ))}
          </ol>
        </details>
      )}
    </article>
  );
}
