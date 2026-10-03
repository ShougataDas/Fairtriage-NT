"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { ArrowDown, ArrowUp, ChevronRight, Hourglass, Phone, RefreshCw, Search, TriangleAlert } from "lucide-react";
import { fetcher, type Contact, type QueueRow, type Tier } from "@/lib/api";
import { TIERS, ago, cx, days, humanise, tierStyle } from "@/lib/format";
import { Card, CardTitle, Empty, ErrorBox, PageHeader, Pill, Spinner, TierBadge, inputClass } from "@/components/ui";
import { DownloadMenu } from "@/components/DownloadMenu";
import { AreaChart } from "@/components/AreaChart";

type Order = "need" | "cost";

export default function QueuePage() {
  const [order, setOrder] = useState<Order>("need");
  const [tier, setTier] = useState<Tier | "">("");
  const [q, setQ] = useState("");
  const [onlyRemote, setOnlyRemote] = useState(false);
  const [area, setArea] = useState("");
  const { data: rows, error, isLoading, mutate, isValidating } = useSWR<QueueRow[]>(`/api/queue?order=${order}`, fetcher, {
    refreshInterval: 15000,
  });
  const { data: contacts } = useSWR<Contact[]>("/api/contacts", fetcher, { refreshInterval: 15000 });

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (rows ?? []).filter(
      (r) =>
        (!tier || r.tier === tier) &&
        (!area || r.area === area) &&
        (!onlyRemote || r.remote) &&
        (!needle || [r.request_id, r.community, r.text, r.trade].some((f) => f.toLowerCase().includes(needle))),
    );
  }, [rows, tier, q, onlyRemote, area]);

  const counts = useMemo(() => {
    const c = { Immediate: 0, Urgent: 0, Routine: 0, past: 0 };
    for (const r of rows ?? []) {
      if (r.tier in c) c[r.tier as keyof typeof c]++;
      if (r.past_target) c.past++;
    }
    return c;
  }, [rows]);

  const movedDown = order === "cost" ? (rows ?? []).filter((r) => r.shift < 0 && r.remote).length : 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Repair queue"
        lede="Ranked by danger, then need, then who reported first. Distance is never part of the rank."
        aside={
          <button
            onClick={() => mutate()}
            className="inline-flex items-center gap-2 self-start rounded-xl border border-line bg-paper px-3 py-2 text-sm font-bold text-ink hover:bg-ink-soft"
          >
            <RefreshCw className={cx("size-4", isValidating && "animate-spin")} aria-hidden /> Refresh
          </button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {TIERS.map((t) => (
          <StatTile
            key={t}
            label={t}
            value={counts[t]}
            tone={tierStyle[t]}
            active={tier === t}
            onClick={() => setTier(tier === t ? "" : t)}
          />
        ))}
        <div className="rounded-2xl border border-line bg-paper p-4">
          <p className="flex items-center gap-1.5 text-sm font-bold text-muted"><Hourglass className="size-4" aria-hidden /> Past target</p>
          <p className="mt-1 text-3xl font-bold">{counts.past}</p>
        </div>
        <div className="rounded-2xl border border-line bg-paper p-4">
          <p className="flex items-center gap-1.5 text-sm font-bold text-muted"><Phone className="size-4" aria-hidden /> To phone</p>
          <p className="mt-1 text-3xl font-bold">{contacts?.length ?? "—"}</p>
        </div>
      </div>

      {contacts && contacts.length > 0 && (
        <Card className="border-urgent/30">
          <CardTitle icon={<Phone className="size-5 text-urgent" aria-hidden />}>Needs a phone call</CardTitle>
          <p className="-mt-2 mb-3 text-muted">Danger to a person comes first. Then reports still unclear after asking once, or a tenant who may have given up. These never leave by themselves.</p>
          <ul className="divide-y divide-line">
            {contacts.map((c) => (
              <li key={c.request_id}>
                <Link href={`/coordinator/requests/${c.request_id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 hover:bg-canvas">
                  <span className="font-mono text-sm">{c.request_id}</span>
                  {c.danger ? (
                    <Pill tone="bad">Danger reported · check 000 was called</Pill>
                  ) : (
                    <Pill tone="warn">{c.status === "needs_phone_call" ? "Still unclear" : "Withdrawal to confirm"}</Pill>
                  )}
                  <span className="text-muted">{[c.address, c.community].filter(Boolean).join(", ")}</span>
                  {c.phone && <span className="font-bold text-ink">{c.phone}</span>}
                  <span className="min-w-0 flex-1 truncate italic">“{c.text}”{c.answer && ` → “${c.answer}”`}</span>
                  <span className="text-sm text-muted">{ago(c.lodged_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {rows && rows.length > 0 && (
        <AreaChart
          rows={rows}
          area={area}
          onArea={(a) => {
            setArea(a);
            if (a) document.getElementById("queue-table")?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
      )}

      <DownloadMenu tier={tier} remote={onlyRemote} q={q} area={area} />

      <Card id="queue-table" className="scroll-mt-24 p-0 sm:p-0">
        {area && (
          <div className="flex items-center justify-between gap-3 border-b border-line bg-ink-soft px-4 py-2 text-sm">
            <span><strong>Showing {area} only.</strong> {shown.length} repair{shown.length === 1 ? "" : "s"}.</span>
            <button onClick={() => setArea("")} className="font-bold text-ink underline">Show all areas</button>
          </div>
        )}
        <div className="flex flex-col gap-3 border-b border-line p-4 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted" aria-hidden />
            <input
              aria-label="Search the queue"
              placeholder="Search reference, community, words, trade"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className={cx(inputClass, "pl-10")}
            />
          </div>
          <label className="flex items-center gap-2 text-sm font-bold">
            <input type="checkbox" checked={onlyRemote} onChange={(e) => setOnlyRemote(e.target.checked)} className="size-4 accent-ink" />
            Remote only
          </label>
          <div role="group" aria-label="Order" className="flex rounded-xl border border-line p-1">
            {(["need", "cost"] as Order[]).map((o) => (
              <button
                key={o}
                onClick={() => setOrder(o)}
                aria-pressed={order === o}
                className={cx("rounded-lg px-3 py-1.5 text-sm font-bold", order === o ? "bg-ink text-white" : "text-muted hover:text-graphite")}
              >
                {o === "need" ? "By need (FairTriage)" : "Nearest first (contrast)"}
              </button>
            ))}
          </div>
        </div>

        {order === "cost" && (
          <div className="flex items-start gap-3 border-b border-line bg-immediate-soft px-4 py-3 text-sm">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-immediate" aria-hidden />
            <p>
              <strong className="text-immediate">This is not how FairTriage ranks.</strong> It shows what an efficiency-first system
              would do: nearest first. {movedDown} remote job{movedDown === 1 ? "" : "s"} would move down.
            </p>
          </div>
        )}

        {isLoading && <div className="px-4"><Spinner label="Loading the queue" /></div>}
        {error && <div className="p-4"><ErrorBox error={error} onRetry={() => mutate()} /></div>}
        {rows && shown.length === 0 && (
          <div className="p-4">
            <Empty title={rows.length ? "Nothing matches these filters" : "The queue is empty"}>
              {rows.length ? "Clear the search or tier filter." : "New reports appear here as soon as they are assessed."}
            </Empty>
          </div>
        )}
        {shown.length > 0 && (
          <>
            <div className="hidden md:block"><QueueTable rows={shown} order={order} /></div>
            <QueueCards rows={shown} order={order} />
          </>
        )}
      </Card>
    </div>
  );
}

function StatTile({ label, value, tone, active, onClick }: { label: string; value: number; tone: (typeof tierStyle)[Tier]; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        "rounded-2xl border p-4 text-left transition hover:shadow-sm",
        active ? cx("border-transparent ring-2 ring-ink", tone.soft) : "border-line bg-paper",
      )}
    >
      <p className={cx("flex items-center gap-1.5 text-sm font-bold", tone.text)}>
        <span className={cx("size-2 rounded-full", tone.dot)} aria-hidden />
        {label}
      </p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
      <p className="text-xs text-muted">{active ? "Showing only these · click to clear" : "Click to filter"}</p>
    </button>
  );
}

function QueueTable({ rows, order }: { rows: QueueRow[]; order: Order }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead className="bg-canvas text-xs uppercase tracking-wide text-muted">
          <tr>
            <th scope="col" className="px-4 py-3">#</th>
            <th scope="col" className="px-4 py-3">Priority</th>
            <th scope="col" className="px-4 py-3">Tenant&apos;s words</th>
            <th scope="col" className="px-4 py-3">Where</th>
            <th scope="col" className="px-4 py-3">Trade</th>
            <th scope="col" className="px-4 py-3">Waiting</th>
            <th scope="col" className="px-4 py-3">Expected</th>
            <th scope="col" className="px-4 py-3"><span className="sr-only">Open</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.request_id} className={cx("group relative hover:bg-canvas", order === "cost" && r.shift < 0 && r.remote && "bg-immediate-soft/60")}>
              <td className="px-4 py-3 align-top">
                <span className="font-bold">{r.display_pos}</span>
                {order === "cost" && r.shift !== 0 && (
                  <span className={cx("ml-1 inline-flex items-center text-xs font-bold", r.shift < 0 ? "text-immediate" : "text-routine")}>
                    {r.shift < 0 ? <ArrowDown className="size-3" aria-hidden /> : <ArrowUp className="size-3" aria-hidden />}
                    {Math.abs(r.shift)}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 align-top">
                <TierBadge tier={r.tier} size="sm" />
                <p className="mt-1 text-xs text-muted">need {r.need.toFixed(0)}</p>
              </td>
              <td className="max-w-md px-4 py-3 align-top">
                <Link href={`/coordinator/requests/${r.request_id}`} className="font-bold text-graphite after:absolute after:inset-0 group-hover:text-ink">
                  “{r.evidence || r.text}”
                </Link>
                <div className="mt-1 flex flex-wrap gap-1">
                  <span className="font-mono text-xs text-muted">{r.request_id}</span>
                  {r.status === "approved" && <Pill tone="good">Approved</Pill>}
                  {r.flags
                    .filter((f) => !["self_reported_vulnerability"].includes(f.code))
                    .slice(0, 3)
                    .map((f) => (
                      <Pill key={f.code} tone={f.code.includes("emergency") || f.code.includes("fallback") ? "bad" : "warn"}>
                        {humanise(f.code)}
                      </Pill>
                    ))}
                </div>
              </td>
              <td className="px-4 py-3 align-top">
                <p>{r.community}</p>
                {r.address && <p className="text-xs text-muted">{r.address}</p>}
                {r.remote && <Pill tone="ink">Remote</Pill>}
              </td>
              <td className="px-4 py-3 align-top">{r.trade || "—"}</td>
              <td className="px-4 py-3 align-top">
                <p className={cx(r.past_target && "font-bold text-immediate")}>{days(r.days_open)}</p>
                <div className="mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-line" aria-hidden>
                  <div
                    className={cx("h-full rounded-full", r.past_target ? "bg-immediate" : r.pct_of_target > 70 ? "bg-urgent" : "bg-routine")}
                    style={{ width: `${Math.min(r.pct_of_target, 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-muted">
                  {r.pct_of_target}% of {r.target_label}
                </p>
              </td>
              <td className="px-4 py-3 align-top">
                {r.wait_low != null ? (
                  <>
                    <p>
                      {r.wait_text
                        ? r.wait_text.charAt(0).toUpperCase() + r.wait_text.slice(1)
                        : r.wait_low === r.wait_high ? `about ${days(r.wait_low)}` : `${r.wait_low}–${r.wait_high} days`}
                    </p>
                    {r.wait_on_trip && <p className="text-xs font-bold text-routine">On a booked trip</p>}
                    {r.remote && r.wait_darwin != null && <p className="text-xs text-muted">Darwin: {r.wait_darwin} days</p>}
                  </>
                ) : "—"}
              </td>
              <td className="px-4 py-3 align-top text-muted">
                <ChevronRight className="size-5 group-hover:text-ink" aria-hidden />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Phones: one card per job, same facts as the table, nothing to scroll sideways. */
function QueueCards({ rows, order }: { rows: QueueRow[]; order: Order }) {
  return (
    <ul className="divide-y divide-line md:hidden">
      {rows.map((r) => (
        <li key={r.request_id}>
          <Link href={`/coordinator/requests/${r.request_id}`} className="flex flex-col gap-2 p-4 hover:bg-canvas">
            <div className="flex items-center gap-2">
              <span className="font-bold">#{r.display_pos}</span>
              {order === "cost" && r.shift !== 0 && (
                <span className={cx("text-xs font-bold", r.shift < 0 ? "text-immediate" : "text-routine")}>
                  {r.shift < 0 ? "▼" : "▲"} {Math.abs(r.shift)}
                </span>
              )}
              <TierBadge tier={r.tier} size="sm" />
              <span className="text-xs text-muted">need {r.need.toFixed(0)}</span>
              <ChevronRight className="ml-auto size-5 text-muted" aria-hidden />
            </div>
            <p className="font-bold">“{r.evidence || r.text}”</p>
            <p className="text-sm text-muted">
              {r.community}{r.remote && " · remote"} · {r.trade || "no trade"} · waiting{" "}
              <span className={cx(r.past_target && "font-bold text-immediate")}>{days(r.days_open)}</span> of {r.target_label}
            </p>
            {r.flags.some((f) => f.code !== "self_reported_vulnerability") && (
              <div className="flex flex-wrap gap-1">
                {r.flags.filter((f) => f.code !== "self_reported_vulnerability").slice(0, 3).map((f) => (
                  <Pill key={f.code} tone={f.code.includes("emergency") || f.code.includes("fallback") ? "bad" : "warn"}>{humanise(f.code)}</Pill>
                ))}
              </div>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}
