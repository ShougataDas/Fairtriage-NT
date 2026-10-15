"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { CheckCircle2, Phone, ShieldAlert, Siren } from "lucide-react";
import { fetcher, post, type SafetyAgency, type SafetyBoard, type SafetyCase, type SafetyReferral } from "@/lib/api";
import { ago, cx, when } from "@/lib/format";
import { Button, Card, CardTitle, Empty, ErrorBox, Field, PageHeader, Pill, Spinner, inputClass } from "@/components/ui";

/** Lives in danger that reached us through the repair form, and who to tell. */
export default function SafetyPage() {
  const { data, error, isLoading, mutate } = useSWR<SafetyBoard>("/api/safety", fetcher, { refreshInterval: 15000 });
  const [show, setShow] = useState<"open" | "done">("open");
  const open = data?.cases.filter((c) => c.open) ?? [];
  const done = data?.cases.filter((c) => !c.open) ?? [];
  const list = show === "open" ? open : done;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Safety reports"
        lede="Messages where someone's life or safety may be in danger. They are not repairs and never enter the queue, and the tenant was told to call 000. Pass each one on to the right authority and record what you did."
      />

      <div className="rounded-2xl border-2 border-immediate/40 bg-immediate-soft p-5">
        <p className="flex items-center gap-2 text-lg font-bold text-immediate">
          <ShieldAlert className="size-5" aria-hidden /> Your duty to report
        </p>
        <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-graphite">
          <li><strong>A life in danger now:</strong> call 000, even if the tenant says they have called.</li>
          <li><strong>A child being harmed or at risk</strong>, including seeing family violence: in the NT any adult who believes this must report it to the Child Protection Hotline, 1800 700 250.</li>
          <li><strong>Serious family violence:</strong> report it to police.</li>
          <li>If you are not sure, call and ask. A report made in good faith is protected.</li>
        </ul>
      </div>

      {isLoading && <Spinner />}
      {error && <ErrorBox error={error} onRetry={() => mutate()} />}
      {data && (
        <>
          <Agencies agencies={data.agencies} />

          <div className="flex gap-2" role="tablist" aria-label="Which reports">
            {(["open", "done"] as const).map((k) => (
              <button key={k} role="tab" aria-selected={show === k} onClick={() => setShow(k)}
                className={cx("rounded-xl px-4 py-2 font-bold", show === k ? "bg-ink text-white" : "border border-line bg-paper text-ink")}>
                {k === "open" ? `To pass on (${open.length})` : `Done (${done.length})`}
              </button>
            ))}
          </div>

          {list.length === 0 ? (
            <Empty icon={<CheckCircle2 className="size-8" aria-hidden />}
              title={show === "open" ? "Nothing to pass on" : "No safety reports recorded yet"}>
              {show === "open" ? "Every safety report has a recorded follow-up." : "Reports appear here once a follow-up is recorded."}
            </Empty>
          ) : (
            <ul className="flex flex-col gap-4">
              {list.map((c) => (
                <li key={c.request_id}><CaseCard c={c} board={data} onSaved={() => mutate()} /></li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function Agencies({ agencies }: { agencies: SafetyAgency[] }) {
  return (
    <Card>
      <CardTitle icon={<Phone className="size-5 text-ink" aria-hidden />}>Who to call</CardTitle>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agencies.map((a) => (
          <li key={a.id} className={cx("rounded-xl border p-3", a.id === "000" ? "border-immediate bg-immediate-soft" : "border-line")}>
            <a href={`tel:${a.phone.replace(/\s/g, "")}`}
              className={cx("text-2xl font-bold tabular-nums underline-offset-4 hover:underline", a.id === "000" ? "text-immediate" : "text-ink")}>
              {a.phone}
            </a>
            <p className="font-bold">{a.name}</p>
            <p className="text-sm text-muted">{a.when}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CaseCard({ c, board, onSaved }: { c: SafetyCase; board: SafetyBoard; onSaved: () => void }) {
  const agencyName = (id: string | null) => board.agencies.find((a) => a.id === id)?.name ?? id;
  return (
    <Card className={c.open ? "border-immediate/50" : undefined}>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="bad">{c.kind === "life_at_risk" ? "Life may be at risk" : "Someone may be hurt"}</Pill>
        {c.open ? <Pill tone="warn">Not yet passed on</Pill> : <Pill tone="good">Followed up</Pill>}
        <Link href={`/coordinator/requests/${c.request_id}`} className="font-mono text-sm text-ink underline">{c.request_id}</Link>
        <span className="text-sm text-muted">reported {ago(c.lodged_at)}</span>
      </div>
      <p className="mt-3 text-lg italic">“{c.text}”</p>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span className="text-muted">{[c.address, c.community].filter(Boolean).join(", ")}</span>
        {c.phone && (
          <a href={`tel:${c.phone.replace(/\s/g, "")}`} className="inline-flex items-center gap-1 font-bold text-ink underline">
            <Phone className="size-4" aria-hidden /> Call the tenant: {c.phone}
          </a>
        )}
      </div>
      {c.repair_too && (
        <p className="mt-2 text-sm text-muted">The message also reported a repair. That repair is in the queue as {c.tier}.</p>
      )}

      {c.referrals.length > 0 && (
        <ol className="mt-4 flex flex-col gap-2 border-l-2 border-line pl-4">
          {c.referrals.map((r: SafetyReferral, i) => (
            <li key={i} className="text-sm">
              <strong>{board.outcomes[r.outcome]}</strong>
              {r.agency && <> to {agencyName(r.agency)}</>}
              {r.reference && <> · reference {r.reference}</>}
              <span className="text-muted"> · {r.actor}, {when(r.at)}</span>
              {r.note && <p className="text-muted">“{r.note}”</p>}
            </li>
          ))}
        </ol>
      )}

      <RecordForm c={c} board={board} onSaved={onSaved} />
    </Card>
  );
}

function RecordForm({ c, board, onSaved }: { c: SafetyCase; board: SafetyBoard; onSaved: () => void }) {
  const [openForm, setOpenForm] = useState(c.open);
  const [outcome, setOutcome] = useState<SafetyReferral["outcome"]>("reported");
  const [agency, setAgency] = useState("000");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const valid = outcome === "reported" ? !!agency : outcome === "no_report_needed" ? note.trim().length >= 10 : true;
  const id = c.request_id;

  if (!openForm) {
    return (
      <button onClick={() => setOpenForm(true)} className="mt-4 text-sm font-bold text-ink underline">
        Record another follow-up
      </button>
    );
  }

  return (
    <form
      className="mt-4 grid gap-3 rounded-xl bg-canvas p-4 sm:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        setBusy(true);
        setError(null);
        try {
          await post(`/api/safety/${id}`, { outcome, agency: outcome === "reported" ? agency : null, reference, note });
          setReference("");
          setNote("");
          setOpenForm(false);
          onSaved();
        } catch (err) {
          setError(err);
        } finally {
          setBusy(false);
        }
      }}
    >
      <fieldset className="sm:col-span-2">
        <legend className="mb-1 font-bold">What did you do?</legend>
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {(Object.keys(board.outcomes) as SafetyReferral["outcome"][]).map((k) => (
            <label key={k} className="flex items-center gap-2">
              <input type="radio" name={`outcome-${id}`} checked={outcome === k} onChange={() => setOutcome(k)} className="size-4" />
              {board.outcomes[k]}
            </label>
          ))}
        </div>
      </fieldset>
      {outcome === "reported" && (
        <Field label="Reported to" htmlFor={`agency-${id}`}>
          <select id={`agency-${id}`} value={agency} onChange={(e) => setAgency(e.target.value)} className={inputClass}>
            {board.agencies.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.phone})</option>)}
          </select>
        </Field>
      )}
      <Field label="Their reference number" hint="Optional, if they gave one" htmlFor={`ref-${id}`}>
        <input id={`ref-${id}`} value={reference} onChange={(e) => setReference(e.target.value)} className={inputClass} />
      </Field>
      <div className="sm:col-span-2">
        <Field label={outcome === "no_report_needed" ? "Why is no report needed?" : "Note"}
          hint={outcome === "no_report_needed" ? "Required, at least 10 characters" : "Optional: what they said, what happens next"}
          htmlFor={`note-${id}`}>
          <textarea id={`note-${id}`} value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={inputClass} />
        </Field>
      </div>
      <div className="flex flex-col gap-2 sm:col-span-2">
        {error != null && <ErrorBox error={error} />}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" busy={busy} disabled={!valid}>
            <Siren className="size-4" aria-hidden /> Save follow-up
          </Button>
          <span className="text-sm text-muted">Saved under your name with the time. It cannot be edited later.</span>
        </div>
      </div>
    </form>
  );
}
