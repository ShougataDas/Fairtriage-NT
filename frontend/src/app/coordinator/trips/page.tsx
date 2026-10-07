"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import useSWR from "swr";
import {
  ArrowRight, CircleCheck, Clock, Flag, Info, MapPin, Plane, Route as RouteIcon, ThumbsUp, TriangleAlert, Truck, Users, Wrench,
} from "lucide-react";
import { fetcher, post, type CommunityGroup, type ConfirmedTrip, type TripPlan, type TripPreview } from "@/lib/api";
import { cx, hoursOrDays, tierStyle, when } from "@/lib/format";
import { Button, Card, CardTitle, Empty, ErrorBox, PageHeader, Pill, Spinner, TierBadge, inputClass } from "@/components/ui";
import { ApprovedTrips } from "@/components/ApprovedTrips";
import { TripCost, moneyRange } from "@/components/TripCost";

// Leaflet needs the browser: load the map on the client only.
const TripMap = dynamic(() => import("@/components/TripMap"), {
  ssr: false,
  loading: () => <div className="grid h-[380px] place-items-center rounded-2xl bg-canvas text-muted">Loading map…</div>,
});

const keyOf = (t: TripPlan) => `${t.anchor}|${t.trade}`;

type Kind = "trip" | "run" | "safe";
const kindOf = (t: TripPlan): Kind => (t.trigger === "daily_run" ? "run" : t.trigger === "make_safe" ? "safe" : "trip");
const KIND_LABEL: Record<Kind, string> = { trip: "Remote trips", run: "Daily runs", safe: "Make-safe call-outs" };

function KindPill({ trip }: { trip: TripPlan }) {
  const k = kindOf(trip);
  if (k === "run") return <Pill tone="good">Daily run</Pill>;
  if (k === "safe") return <Pill tone="bad">Make-safe call-out</Pill>;
  return <Pill tone="neutral">Remote trip</Pill>;
}

export default function TripsPage() {
  const { data, error, isLoading, mutate } = useSWR<TripPreview>("/api/trips/preview", fetcher, { refreshInterval: 30000 });
  const { data: confirmed, mutate: mutateConfirmed } = useSWR<ConfirmedTrip[]>("/api/trips", fetcher);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<"recommended" | "approved">("recommended");
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  const [kind, setKind] = useState<Kind | "all">("all");
  const allTrips = useMemo(() => (data?.trips ?? []).filter((t) => t.route), [data]);
  const trips = useMemo(() => allTrips.filter((t) => kind === "all" || kindOf(t) === kind), [allTrips, kind]);
  const activeApproved = (confirmed ?? []).filter((t) => (t.status ?? "approved") === "approved").length;
  const unreachable = (data?.trips ?? []).filter((t) => !t.route);
  const current = trips.find((t) => keyOf(t) === selected) ?? trips[0];

  useEffect(() => {
    if (!selected && trips[0]) setSelected(keyOf(trips[0]));
  }, [trips, selected]);

  async function approve(anchor?: string) {
    setBusy(true);
    setActionError(null);
    try {
      const r = await post<TripPlan[]>(`/api/trips/plan${anchor ? `?anchor=${encodeURIComponent(anchor)}` : ""}`);
      const n = r.filter((t) => t.route).length;
      setNotice(anchor ? `Trip approved. ${r[0]?.stops.length ?? 0} tenants can now see when to expect someone. See it under Approved.` : `${n} trips approved. See them under Approved.`);
      setConfirmAll(false);
      setSelected(null);
      await Promise.all([mutate(), mutateConfirmed()]);
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  const totals = useMemo(() => {
    const jobs = allTrips.reduce((n, t) => n + t.stops.length, 0);
    const saved = allTrips.reduce((n, t) => n + (t.benefit?.hours_saved ?? 0), 0);
    return { jobs, saved: Math.round(saved), air: allTrips.filter((t) => t.route?.by_air).length, late: allTrips.filter((t) => t.target_missed).length };
  }, [allTrips]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Trip planner"
        lede="Plans the crews' work: long trips to remote communities, daily runs around Darwin, Palmerston and nearby towns, and make-safe call-outs for Immediate jobs."
        aside={view === "recommended" && allTrips.length > 1 && <Button variant="secondary" onClick={() => setConfirmAll(true)} className="self-start">Approve all {allTrips.length}</Button>}
      />

      <section aria-label="About this page" className="rounded-2xl border border-line bg-paper p-5 shadow-sm">
        <p className="text-lg">
          Sending a crew out bush takes hours or days, so each trip should fix as much as it safely can. This page groups
          waiting repairs into trips: it starts with the most urgent job, looks at the roads to get there, and adds other
          repairs along the way when that does not make anyone wait too long.
        </p>
        <ol className="mt-4 grid gap-3 sm:grid-cols-3">
          {[
            ["1", "Pick a recommended trip", "The list shows each trip the system suggests, most urgent first."],
            ["2", "Check the map and the reasons", "See the route, every stop, and what the trip saves compared with separate trips."],
            ["3", "Approve it", "The jobs are booked and each tenant sees when to expect someone."],
          ].map(([n, t, b]) => (
            <li key={n} className="flex gap-3 rounded-xl bg-canvas p-3">
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-ink text-sm font-bold text-white">{n}</span>
              <span><strong className="block">{t}</strong><span className="text-sm text-muted">{b}</span></span>
            </li>
          ))}
        </ol>
      </section>

      <div role="tablist" aria-label="Trips" className="flex gap-1 border-b border-line sm:gap-2">
        {([
          ["recommended", "Recommended", trips.length],
          ["approved", "Approved", activeApproved],
        ] as const).map(([v, label, n]) => (
          <button
            key={v}
            role="tab"
            aria-selected={view === v}
            onClick={() => setView(v)}
            className={cx(
              "-mb-px flex min-w-0 items-center gap-2 border-b-4 px-2 py-3 text-base font-bold sm:px-4 sm:text-lg",
              view === v ? "border-ink text-ink" : "border-transparent text-muted hover:text-graphite",
            )}
          >
            {label}
            <span className={cx("rounded-full px-2.5 py-0.5 text-sm", view === v ? "bg-ink text-white" : "bg-canvas text-muted")}>{n}</span>
          </button>
        ))}
      </div>

      {view === "approved" && <ApprovedTrips trips={confirmed ?? []} onChanged={() => Promise.all([mutate(), mutateConfirmed()])} />}

      {view === "recommended" && (<>
      {confirmAll && (
        <div role="alertdialog" aria-labelledby="all-title" className="flex flex-col gap-3 rounded-2xl border-2 border-ink bg-ink-soft p-5 sm:flex-row sm:items-center">
          <div className="flex-1">
            <p id="all-title" className="font-bold">Approve all {allTrips.length} trips, covering {totals.jobs} repairs?</p>
            <p className="text-muted">Each job is booked with its expected arrival, and tenants see it straight away.</p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setConfirmAll(false)}>Cancel</Button>
            <Button busy={busy} onClick={() => approve()}>Yes, approve all</Button>
          </div>
        </div>
      )}
      {notice && (
        <p role="status" className="flex items-center gap-2 rounded-xl bg-routine-soft p-4 font-bold text-routine">
          <CircleCheck className="size-5" aria-hidden /> {notice}
        </p>
      )}
      {actionError != null && <ErrorBox error={actionError} />}

      {data && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Tile icon={<RouteIcon className="size-4" aria-hidden />} label="Trips recommended" value={allTrips.length} />
          <Tile icon={<Wrench className="size-4" aria-hidden />} label="Repairs covered" value={totals.jobs} />
          <Tile icon={<Clock className="size-4" aria-hidden />} label="Travel saved vs one trip per job" value={`${totals.saved} h`} good />
          <Tile icon={<TriangleAlert className="size-4" aria-hidden />} label="Trips that cannot meet a target" value={totals.late} warn />
        </div>
      )}

      {data && <Crews teams={data.teams} onMoved={() => mutate()} />}

      {isLoading && <Spinner label="Working out routes" />}
      {error && <ErrorBox error={error} onRetry={() => mutate()} />}
      {allTrips.length > 0 && (
        <div role="group" aria-label="Show" className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-sm font-bold">Show</span>
          {(["all", "trip", "run", "safe"] as const).map((k) => {
            const n = k === "all" ? allTrips.length : allTrips.filter((t) => kindOf(t) === k).length;
            return (
              <button
                key={k}
                onClick={() => {
                  setKind(k);
                  setSelected(null);
                }}
                aria-pressed={kind === k}
                className={cx(
                  "rounded-full border-2 px-3 py-1 text-sm font-bold transition",
                  kind === k ? "border-ink bg-ink text-white" : "border-line text-graphite hover:border-ink",
                )}
              >
                {k === "all" ? "All" : KIND_LABEL[k]} <span className="font-normal opacity-80">{n}</span>
              </button>
            );
          })}
        </div>
      )}

      {data && trips.length === 0 && (
        <Empty icon={<RouteIcon className="size-8" aria-hidden />} title="No trip is needed right now">
          {kind === "all"
            ? `Trips start for an Immediate or Urgent job outside daily reach, or when a community has waited ${data.rules.community_threshold_multiple}× its target. Jobs in town go on daily runs.`
            : `No ${KIND_LABEL[kind as Kind].toLowerCase()} right now.`}
        </Empty>
      )}

      {trips.length > 0 && current && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
          <nav aria-label="Recommended trips" className="flex flex-col gap-2 lg:max-h-[calc(100vh-8rem)] lg:overflow-auto lg:pr-1">
            {trips.map((t) => (
              <TripListItem
                key={keyOf(t)}
                trip={t}
                active={keyOf(t) === keyOf(current)}
                onSelect={() => {
                  setSelected(keyOf(t));
                  if (window.innerWidth < 1024) detailRef.current?.scrollIntoView({ behavior: "smooth" });
                }}
              />
            ))}
          </nav>
          <div ref={detailRef} className="min-w-0 scroll-mt-24">
            <TripDetail trip={current} busy={busy} onApprove={() => approve(current.anchor)} />
          </div>
        </div>
      )}

      {unreachable.length > 0 && (
        <Card className="border-immediate/40">
          <CardTitle icon={<TriangleAlert className="size-5 text-immediate" aria-hidden />}>Cannot be reached</CardTitle>
          {unreachable.map((t) => <p key={keyOf(t)}>{t.headline}. {t.explanation}</p>)}
        </Card>
      )}

      {data && <Rules rules={data.rules} />}
      </>)}

    </div>
  );
}

function places(t: TripPlan): string[] {
  const out = [t.start];
  for (const s of t.stops) if (s.community !== out[out.length - 1]) out.push(s.community);
  return out;
}

function TripListItem({ trip: t, active, onSelect }: { trip: TripPlan; active: boolean; onSelect: () => void }) {
  const tier = t.stops.find((s) => s.request_id === t.anchor)?.tier ?? "Routine";
  const p = places(t);
  return (
    <button
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={cx(
        "flex flex-col gap-2 rounded-2xl border p-4 text-left transition",
        active ? "border-ink bg-paper shadow-md ring-2 ring-ink" : "border-line bg-paper hover:border-ink/50",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <TierBadge tier={tier} size="sm" />
        <KindPill trip={t} />
        {t.route?.by_air && <Pill tone="ink"><Plane className="size-3" aria-hidden /> Charter</Pill>}
        {t.target_missed && <Pill tone="bad">Late</Pill>}
        <span className="ml-auto text-xs text-muted">{t.trade}</span>
      </div>
      <p className="font-bold leading-snug">
        {p.map((x, i) => (
          <span key={i}>
            {i > 0 && <ArrowRight className="mx-1 inline size-3.5 text-muted" aria-label="then" />}
            {x.replace("Darwin (Ludmilla)", "Darwin depot")}
          </span>
        ))}
      </p>
      <p className="flex flex-wrap gap-x-3 text-sm text-muted">
        <span>{t.stops.length} repair{t.stops.length > 1 ? "s" : ""}</span>
        <span>{t.route?.hours.toFixed(1)} h travel</span>
        {t.benefit && t.benefit.hours_saved >= 0.5 && <span className="font-bold text-routine">saves {t.benefit.hours_saved} h</span>}
        {t.cost && <span>≈ {moneyRange(t.cost.low, t.cost.high)}</span>}
      </p>
    </button>
  );
}

function TripDetail({ trip: t, busy, onApprove }: { trip: TripPlan; busy: boolean; onApprove: () => void }) {
  const b = t.benefit;
  const anchor = t.stops.find((s) => s.request_id === t.anchor);
  return (
    <div className="flex flex-col gap-5">
      <Card className="p-4 sm:p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-bold">{t.headline.replace("Recommended trip: ", "")}</h2>
          <KindPill trip={t} />
          {t.route?.by_air && <Pill tone="ink"><Plane className="size-3" aria-hidden /> Charter flight</Pill>}
        </div>
        <TripMap trip={t} />
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
          <span className="flex items-center gap-1.5"><span className="inline-block h-1 w-6 rounded bg-ink" /> Recommended route</span>
          <span className="flex items-center gap-1.5"><span className="inline-block w-6 border-t-2 border-dashed border-ink" /> Charter flight</span>
          <span className="flex items-center gap-1.5"><span className="inline-block w-6 border-t-2 border-dotted border-muted" /> Routes not chosen</span>
          <span>★ crew start · numbers = stops in order · ⚑ destination · several repairs in one place fan out around it</span>
        </div>
      </Card>

      {b && (
        <Card className="border-routine/40">
          <CardTitle icon={<ThumbsUp className="size-5 text-routine" aria-hidden />}>Why approve this trip</CardTitle>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <Benefit label="Repairs in one trip" value={String(b.jobs)} sub={b.jobs > 1 ? `instead of ${b.separate_trips} trips` : "one job"} />
            <Benefit
              label="Travel saved"
              value={b.hours_saved >= 0.5 ? `${b.hours_saved} h` : "—"}
              sub={b.hours_saved >= 0.5 ? `${b.km_saved.toLocaleString()} km less` : `${b.trip_hours} h round trip`}
              good={b.hours_saved >= 0.5}
            />
            <Benefit
              label="Tenants reached sooner"
              value={String(b.sooner_jobs)}
              sub={b.sooner_jobs ? `${b.sooner_days} days sooner in total` : "than they were told"}
              good={b.sooner_jobs > 0}
            />
            <Benefit
              label={`${anchor?.tier ?? ""} job in ${t.community}`}
              value={b.destination_on_time ? "On time" : "Late"}
              sub={b.destination_delay_h >= 0.1 ? `stops add ${b.destination_delay_h} h` : "straight there"}
              good={b.destination_on_time}
              bad={!b.destination_on_time}
            />
          </div>
          <ul className="mt-4 flex flex-col gap-2">
            {b.why.map((line, i) => (
              <li key={i} className="flex items-start gap-2">
                <CircleCheck className="mt-1 size-4 shrink-0 text-routine" aria-hidden /> <span>{line}</span>
              </li>
            ))}
          </ul>
          <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-line pt-4">
            <Button busy={busy} onClick={onApprove}>
              <CircleCheck className="size-5" aria-hidden /> Approve this trip
            </Button>
            <span className="text-sm text-muted">Books {b.jobs} job{b.jobs > 1 ? "s" : ""} and shows each tenant when to expect someone.</span>
          </div>
        </Card>
      )}

      {t.cost && <TripCost cost={t.cost} />}

      <Card>
        <CardTitle icon={<Truck className="size-5 text-ink" aria-hidden />}>Itinerary</CardTitle>
        <ol className="relative flex flex-col gap-5 border-l-2 border-line pl-6">
          <li className="relative">
            <span className="absolute -left-[33px] grid size-6 place-items-center rounded-md bg-graphite text-xs text-white">★</span>
            <p className="font-bold">Leave {t.start}</p>
            <p className="text-sm text-muted">
              {t.crew_region} crew {t.crew}, {t.trade}{t.start_offset_h > 0 ? ` · free to leave in ${hoursOrDays(t.start_offset_h, t.workday_hours)}` : " · ready now"}
            </p>
          </li>
          {t.stops.map((s) => (
            <li key={s.request_id} className="relative">
              <span className={cx("absolute -left-[35px] grid size-7 place-items-center rounded-full text-xs font-bold text-white ring-4 ring-paper", tierStyle[s.tier].dot)}>
                {s.request_id === t.anchor ? <Flag className="size-3.5" aria-hidden /> : s.order}
              </span>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-bold">
                  {s.community}
                  {s.address && <span className="font-normal text-muted"> · {s.address}</span>}
                </p>
                <p className="text-sm font-bold">arrive {hoursOrDays(s.eta_hours, t.workday_hours)}</p>
              </div>
              <p className="italic">“{s.evidence}”</p>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                <TierBadge tier={s.tier} size="sm" />
                <Link href={`/coordinator/requests/${s.request_id}`} className="font-mono text-ink hover:underline">{s.request_id}</Link>
                <span className="text-muted">{s.reason}</span>
                {s.prev_wait_days != null && <span className="text-muted">· was told {s.prev_wait_days.toFixed(1)} days</span>}
                {s.on_time ? <Pill tone="good">Inside target</Pill> : s.slack_hours <= 0 ? <Pill tone="warn">Already past target</Pill> : <Pill tone="bad">After target</Pill>}
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <Card>
        <CardTitle icon={<Info className="size-5 text-ink" aria-hidden />}>How the route was chosen</CardTitle>
        <p className="text-lg">{t.explanation}</p>
        {t.options.length > 1 && (
          <ul className="mt-4 flex flex-col gap-2">
            {t.options.map((o) => {
              const longest = Math.max(...t.options.map((x) => x.hours));
              return (
                <li key={o.name} className={cx("rounded-xl border p-3", o.chosen ? "border-ink bg-ink-soft" : "border-line")}>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="font-bold">{o.chosen && <CircleCheck className="mr-1 inline size-4 text-ink" aria-hidden />}{o.name}</span>
                    <span className="text-muted">
                      {o.hours.toFixed(1)} h{o.extra_hours > 0 && ` (+${o.extra_hours.toFixed(1)})`} · passes {o.passes} job{o.passes === 1 ? "" : "s"}
                    </span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-line" aria-hidden>
                    <div className={cx("h-full rounded-full", o.chosen ? "bg-ink" : "bg-muted/50")} style={{ width: `${(o.hours / longest) * 100}%` }} />
                  </div>
                  <p className="mt-1 text-xs text-muted">{o.chosen ? "Chosen" : !o.feasible ? o.note : "Serves fewer jobs for the extra time"}</p>
                </li>
              );
            })}
          </ul>
        )}
        {t.left_behind.length > 0 && (
          <details className="mt-4">
            <summary className="cursor-pointer font-bold text-ink">Jobs nearby that are not on this trip ({t.left_behind.length})</summary>
            <ul className="mt-2 flex flex-col gap-1.5 text-sm">
              {t.left_behind.map((j) => (
                <li key={j.request_id} className="flex flex-wrap items-center gap-2">
                  <TierBadge tier={j.tier} size="sm" />
                  <Link href={`/coordinator/requests/${j.request_id}`} className="font-mono text-ink hover:underline">{j.request_id}</Link>
                  <span className="text-muted">{j.community}:</span> <span>{j.reason}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </Card>
    </div>
  );
}

function Benefit({ label, value, sub, good, bad }: { label: string; value: string; sub: string; good?: boolean; bad?: boolean }) {
  return (
    <div className={cx("rounded-xl p-3", good ? "bg-routine-soft" : bad ? "bg-immediate-soft" : "bg-canvas")}>
      <p className="text-xs font-bold uppercase tracking-wide text-muted">{label}</p>
      <p className={cx("mt-1 text-2xl font-bold", good && "text-routine", bad && "text-immediate")}>{value}</p>
      <p className="text-sm text-muted">{sub}</p>
    </div>
  );
}

function Tile({ label, value, icon, warn, good }: { label: string; value: number | string; icon: React.ReactNode; warn?: boolean; good?: boolean }) {
  const hot = warn && Number(value) > 0;
  return (
    <div className={cx("rounded-2xl border p-4", hot ? "border-immediate/30 bg-immediate-soft" : "border-line bg-paper")}>
      <p className={cx("flex items-center gap-1.5 text-sm font-bold", hot ? "text-immediate" : good ? "text-routine" : "text-muted")}>{icon}{label}</p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}

function Crews({ teams, onMoved }: { teams: Record<string, string>; onMoved: () => void }) {
  const { data: groups } = useSWR<CommunityGroup[]>("/api/communities", fetcher);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function move(region: string, location: string) {
    setBusy(region);
    setError(null);
    try {
      await post(`/api/teams/${encodeURIComponent(region)}?location=${encodeURIComponent(location)}`);
      onMoved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <details className="rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5">
      <summary className="flex cursor-pointer flex-wrap items-center gap-x-4 gap-y-1">
        <span className="flex items-center gap-2 font-bold"><Users className="size-5 text-ink" aria-hidden /> Where the crews are</span>
        {Object.entries(teams).map(([r, l]) => (
          <span key={r} className="flex items-center gap-1 text-sm text-muted"><MapPin className="size-3.5" aria-hidden />{r}: {l}</span>
        ))}
        <span className="text-sm font-bold text-ink">Change</span>
      </summary>
      <p className="mb-4 mt-3 text-muted">Trips start from here. Move a crew and every route and arrival time is worked out again.</p>
      <div className="grid gap-4 sm:grid-cols-3">
        {Object.entries(teams).map(([region, loc]) => (
          <label key={region} className="flex flex-col gap-1.5">
            <span className="font-bold">{region} crews {busy === region && <span className="font-normal text-muted">· updating…</span>}</span>
            <select value={loc} disabled={busy !== null} onChange={(e) => move(region, e.target.value)} className={inputClass}>
              {(groups ?? []).map((g) => (
                <optgroup key={g.group} label={g.group}>
                  {g.communities.map((c) => <option key={c.name}>{c.name}</option>)}
                </optgroup>
              ))}
              {!groups && <option>{loc}</option>}
            </select>
          </label>
        ))}
      </div>
      {error != null && <div className="mt-3"><ErrorBox error={error} /></div>}
    </details>
  );
}

function Rules({ rules: t }: { rules: TripPreview["rules"] }) {
  const r = t.routing;
  return (
    <details className="rounded-2xl border border-line bg-paper p-5 shadow-sm">
      <summary className="cursor-pointer font-bold">How trips are chosen (every rule, with its value)</summary>
      <ul className="mt-3 flex list-disc flex-col gap-2 pl-5">
        <li>A trip starts for an Immediate or Urgent job outside daily reach, or when a community&apos;s oldest job has waited {t.community_threshold_multiple}× its target. An urgent job that does not fit on a full trip gets a trip of its own.</li>
        <li>In Darwin, Palmerston and towns within daily reach, each daily run starts with the highest-ranked job still waiting for that trade, then adds nearby jobs of the same trade in need order while the day has room. The visiting order is by road; it never changes who is served.</li>
        <li>An Immediate job in town is a make-safe call-out: an on-call tradesperson goes straight there. It is never bundled into a run.</li>
        <li>{r.direct_tiers.join(", ")} jobs go by the fastest route with no stops before them.</li>
        <li>Otherwise jobs on a route are added in need order, never quickest first, while the destination still arrives within {Math.round((1 - r.anchor_slack_reserve) * 100)}% of its remaining time to target (already overdue: at most {r.overdue_delay_cap_hours} h later), and no job on the trip is pushed past its target.</li>
        <li>Route score = value of jobs served on the way − {r.extra_hour_cost} per extra hour − {r.charter_cost} for a charter. A job is worth {r.stop_value.Immediate} / {r.stop_value.Urgent} / {r.stop_value.Routine} by tier, up to {Math.round(r.wait_bonus_cap * 100)}% more for time waited.</li>
        <li>A trip holds {t.capacity_hours_per_day * t.trip_days} hours of on-site work. Arrival times count {t.workday_hours} crew hours a day. Restricted roads at {Math.round(r.restricted_speed_factor * 100)}% speed; closed roads unused.</li>
        <li>If a long trip would leave a later urgent job waiting past its target for the same crew, the long trip is shortened.</li>
      </ul>
      <p className="mt-3 text-sm text-muted">Road distances and speeds are approximate. None of this changes a job&apos;s tier, need score or rank.</p>
    </details>
  );
}
