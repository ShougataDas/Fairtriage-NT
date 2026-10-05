"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { ArrowLeft, CircleCheck, Flag, Gauge, MapPin, Truck } from "lucide-react";
import { fetcher, post, type RequestView, type Tier } from "@/lib/api";
import { TIERS, cx, day, humanise, readerName, statusLabel, when } from "@/lib/format";
import { Docket } from "@/components/Docket";
import { Button, Card, CardTitle, ErrorBox, Pill, Spinner, TierBadge, inputClass } from "@/components/ui";

export default function RequestDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: r, error, isLoading, mutate } = useSWR<RequestView>(`/api/requests/${id}`, fetcher);

  if (isLoading) return <Spinner label="Loading the request" />;
  if (error) return <ErrorBox error={error} onRetry={() => mutate()} />;
  if (!r) return null;
  const a = r.assessment;
  const f = a?.facts ?? {};

  return (
    <div className="flex flex-col gap-6">
      <Link href="/coordinator" className="inline-flex items-center gap-1 self-start font-bold text-ink hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Back to the queue
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-2xl font-bold sm:text-3xl">{r.request_id}</h1>
        {a && <TierBadge tier={a.tier} size="lg" />}
        <Pill tone={r.status === "approved" || r.status === "scheduled" ? "good" : "neutral"}>{statusLabel[r.status] ?? r.status}</Pill>
      </div>
      <p className="-mt-3 flex items-center gap-1 text-muted">
        <MapPin className="size-4" aria-hidden /> {[r.address, r.community].filter(Boolean).join(", ")} · lodged {when(r.lodged_at)}
        {r.phone && <> · <a className="font-bold text-ink underline" href={`tel:${r.phone.replace(/\s/g, "")}`}>{r.phone}</a></>}
        {r.prior_deferrals > 0 && <span className="ml-2"><Pill tone="warn">Deferred {r.prior_deferrals}×</Pill></span>}
      </p>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardTitle>What the tenant wrote</CardTitle>
            <blockquote className="border-l-4 border-ink pl-4 text-xl italic">“{r.text_original}”</blockquote>
            {r.text_normalised && r.text_normalised !== r.text_original && (
              <p className="mt-3 text-sm text-muted">Spelling-normalised reading: “{r.text_normalised}”</p>
            )}
            {r.question && (
              <div className="mt-4 rounded-xl bg-canvas p-4">
                <p><strong>We asked:</strong> {r.question}</p>
                <p><strong>Tenant answered:</strong> {r.answer ?? <span className="text-muted">waiting for the tenant</span>}</p>
              </div>
            )}
            {f.evidence && f.evidence !== r.text_original && (
              <p className="mt-3"><strong>Evidence used:</strong> <span className="italic">“{f.evidence}”</span></p>
            )}
          </Card>

          {a && a.tier !== "NotInQueue" && (
            <Card>
              <CardTitle icon={<Gauge className="size-5 text-ink" aria-hidden />} aside={<span className="text-3xl font-bold">{a.need.toFixed(0)}<span className="text-base text-muted">/100</span></span>}>
                Why this priority
              </CardTitle>
              <p className="text-lg">{f.tier_reason ? f.tier_reason.charAt(0).toUpperCase() + f.tier_reason.slice(1) : ""}.</p>
              <p className="mt-1 text-sm text-muted">The tier decides the group. The need score orders jobs within it.</p>
              <div className="mt-5 flex flex-col gap-3">
                {(f.components ?? []).map((c) => (
                  <div key={c.name}>
                    <div className="flex justify-between text-sm">
                      <span><span className="font-bold capitalize">{c.name}</span> <span className="text-muted">· {c.detail}</span></span>
                      <span className="tabular-nums text-muted">
                        {c.raw.toFixed(2)} × {c.weight.toFixed(2)} = <strong className="text-graphite">{(c.contribution * 100).toFixed(1)}</strong>
                      </span>
                    </div>
                    <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-line" aria-hidden>
                      <div className="h-full rounded-full bg-ink" style={{ width: `${c.weight ? (c.contribution / c.weight) * 100 : 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-5 flex items-start gap-3 rounded-xl bg-routine-soft p-4 text-sm">
                <CircleCheck className="mt-0.5 size-5 shrink-0 text-routine" aria-hidden />
                <p>
                  <strong className="text-routine">No distance term exists in this calculation.</strong> Rank {f.rank} of {f.tier_size};
                  the same job with location removed would also be {f.darwin_rank}.
                </p>
              </div>
            </Card>
          )}

          {a?.reachability && (
            <Card>
              <CardTitle icon={<MapPin className="size-5 text-ink" aria-hidden />}>Reachability, shown separately</CardTitle>
              <dl className="grid gap-4 sm:grid-cols-3">
                <Stat label="Access" value={a.reachability.access} />
                <Stat label="Road distance (est.)" value={`${a.reachability.road_km_est.toFixed(0)} km`} />
                <Stat label="Road" value={a.reachability.road_status} />
              </dl>
              {r.wait_now && (
                <p className="mt-4">
                  Expected from today <strong>{r.wait_now.range_text}</strong>
                  {f.wait && <> (told on the day: {f.wait.range_text})</>}. Recalculated from the current queue.
                </p>
              )}
              {f.wait && (
                <p className="mt-2">
                  When reported: <strong>{f.wait.range_text}</strong>. The same job in Darwin: about {f.wait.darwin} days
                  {f.wait.gap_days > 0 && <> (gap {f.wait.gap_days} days, from travel, roads and crew numbers)</>}.
                </p>
              )}
              <p className="mt-2 text-sm text-muted">Reachability affects when someone can arrive. It never changes the tier or the need score.</p>
            </Card>
          )}

          {r.trip && (
            <Card className="border-routine/30">
              <CardTitle icon={<Truck className="size-5 text-routine" aria-hidden />}>On a confirmed trip</CardTitle>
              <p>
                {r.trip.trip_id}: stop {r.trip.stop} of {r.trip.stops}. Expected arrival {when(r.trip.eta_at)} (about {r.trip.eta_days} days from now).
              </p>
              {r.trip.tenant_update && <p className="mt-2 text-sm text-muted">The tenant sees: “{r.trip.tenant_update}”</p>}
            </Card>
          )}

          {a && a.flags.length > 0 && (
            <Card>
              <CardTitle icon={<Flag className="size-5 text-urgent" aria-hidden />}>Flags</CardTitle>
              <ul className="flex flex-col gap-3">
                {a.flags.map((fl, i) => (
                  <li key={i} className="flex flex-col gap-0.5 rounded-xl border border-line p-3">
                    <span className="font-bold">{humanise(fl.code)}</span>
                    {fl.detail != null && <span className="text-muted">{typeof fl.detail === "string" ? fl.detail : JSON.stringify(fl.detail)}</span>}
                    {fl.action && <span className="text-sm text-ink">→ {humanise(fl.action)}</span>}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {r.decisions.length > 0 && (
            <Card>
              <CardTitle>Decision history</CardTitle>
              <ol className="relative flex flex-col gap-4 border-l-2 border-line pl-5">
                {r.decisions.map((d, i) => (
                  <li key={i}>
                    <span className="absolute -left-[7px] mt-1.5 size-3 rounded-full bg-ink" aria-hidden />
                    <p className="font-bold">
                      {d.action === "override" ? `Changed ${d.from} → ${d.to}` : humanise(d.action)} <span className="font-normal text-muted">by {d.actor}</span>
                    </p>
                    <p className="text-sm text-muted">{when(d.at)}</p>
                    {d.reason && <p className="mt-1 italic">“{d.reason}”</p>}
                  </li>
                ))}
              </ol>
            </Card>
          )}

          <details className="rounded-2xl border border-line bg-paper p-5 shadow-sm">
            <summary className="cursor-pointer font-bold">How the message was read ({r.extractions.length})</summary>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-muted">
                  <tr><th className="py-2 pr-4">Text read</th><th className="pr-4">Read by</th><th className="pr-4">Fallback</th><th className="pr-4">Danger</th><th className="pr-4">Essential</th><th>Domain</th></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {r.extractions.map((e, i) => (
                    <tr key={i}>
                      <td className="py-2 pr-4">{e.source}</td>
                      <td className="pr-4">{readerName(e.extractor)}{e.cache_hit && " (cached)"}</td>
                      <td className="pr-4">{e.fallback ? <Pill tone="bad">yes</Pill> : "no"}</td>
                      <td className="pr-4">{String(e.payload.endangers_person)}</td>
                      <td className="pr-4">{String(e.payload.essential_service_lost)}</td>
                      <td>{String(e.payload.hazard_domain)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-sm text-muted">Every reading is kept. If the original and the spelling-corrected text disagree, the more cautious reading is used and the job is flagged.</p>
            </div>
          </details>
        </div>

        <aside className="flex flex-col gap-6 lg:sticky lg:top-24 lg:self-start">
          {a && <DecisionPanel id={r.request_id} current={a.tier} onDone={() => mutate()} />}
          {a && (
            <div>
              <h2 className="mb-2 font-bold">What the tenant sees</h2>
              <div className="max-h-[32rem] overflow-auto rounded-2xl text-[15px]">
                <Docket
                  requestId={r.request_id} tier={a.tier} explanation={a.explanation_tenant} address={r.address} community={r.community}
                  toldOn={r.wait_now ? day(a.created_at) : undefined}
                />
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-canvas p-3">
      <dt className="text-xs font-bold uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-lg font-bold first-letter:uppercase">{value}</dd>
    </div>
  );
}

type Action = "approve" | "override" | "request_info";

function DecisionPanel({ id, current, onDone }: { id: string; current: Tier; onDone: () => void }) {
  const [action, setAction] = useState<Action>("approve");
  const [toTier, setToTier] = useState<string>("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const downgrade = action === "override" && current === "Immediate" && toTier && toTier !== "Immediate";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      await post(`/api/requests/${id}/decision`, {
        action,
        to_tier: action === "override" ? toTier || null : null,
        reason: reason.trim() || null,
      });
      setSaved(action === "approve" ? "Approved." : action === "override" ? `Changed to ${toTier}.` : "Marked as waiting for the tenant.");
      setReason("");
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const options: [Action, string][] = [
    ["approve", "Approve"],
    ["override", "Change tier"],
    ["request_info", "Ask tenant"],
  ];

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 rounded-2xl border-2 border-ink bg-paper p-5 shadow-sm">
      <h2 className="text-lg font-bold">Your decision</h2>
      <div role="radiogroup" aria-label="Action" className="grid grid-cols-3 gap-1 rounded-xl bg-canvas p-1">
        {options.map(([v, label]) => (
          <button
            key={v}
            type="button"
            role="radio"
            aria-checked={action === v}
            onClick={() => setAction(v)}
            className={cx("rounded-lg px-2 py-2 text-sm font-bold", action === v ? "bg-paper text-ink shadow-sm" : "text-muted")}
          >
            {label}
          </button>
        ))}
      </div>

      {action === "override" && (
        <div className="flex flex-col gap-1.5">
          <span className="font-bold">New tier</span>
          <div className="grid grid-cols-3 gap-2">
            {TIERS.filter((t) => t !== current).concat().map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setToTier(t)}
                aria-pressed={toTier === t}
                className={cx("rounded-xl border-2 px-2 py-2 text-sm font-bold", toTier === t ? "border-ink bg-ink-soft text-ink" : "border-line")}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <label htmlFor="reason" className="font-bold">
          {action === "request_info" ? "Question for the tenant" : "Reason"}{" "}
          {action === "override" ? (
            <span className="font-normal text-immediate">required · the tenant is shown this</span>
          ) : action === "request_info" ? (
            <span className="font-normal text-immediate">required · the tenant answers it, and the job is assessed again</span>
          ) : (
            <span className="font-normal text-muted">optional</span>
          )}
        </label>
        <textarea id="reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={400} className={inputClass} />
        {downgrade && (
          <p className="rounded-lg bg-urgent-soft p-2 text-sm text-urgent">
            Downgrading an Immediate job needs a second reviewer. Name them in the reason, e.g. “second reviewer: J. Smith”.
          </p>
        )}
      </div>

      {error != null && <ErrorBox error={error} />}
      {saved && <p role="status" className="flex items-center gap-2 font-bold text-routine"><CircleCheck className="size-5" aria-hidden /> {saved}</p>}
      <Button
        type="submit"
        busy={busy}
        disabled={(action === "override" && (!toTier || reason.trim().length < 5)) || (action === "request_info" && reason.trim().length < 5)}
      >
        Record decision
      </Button>
    </form>
  );
}
