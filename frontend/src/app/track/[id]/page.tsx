"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { ArrowRight, CalendarClock, CircleCheck, Truck } from "lucide-react";
import { fetcher, post, type RequestView } from "@/lib/api";
import { cx, statusLabel, when } from "@/lib/format";
import { Docket } from "@/components/Docket";
import { Button, ButtonLink, Empty, ErrorBox, Spinner, inputClass } from "@/components/ui";

export default function TrackRecord() {
  const { id } = useParams<{ id: string }>();
  const { data, error, isLoading, mutate } = useSWR<RequestView>(`/api/requests/${id}`, fetcher, { refreshInterval: 30000 });

  if (isLoading) return <Spinner label="Finding your repair" />;
  if (error) {
    return (error as { status?: number }).status === 404 ? (
      <Empty title="No repair with that reference">
        Check the number and try again. <ButtonLink href="/track" variant="secondary" className="mt-4">Try another number</ButtonLink>
      </Empty>
    ) : (
      <ErrorBox error={error} onRetry={() => mutate()} />
    );
  }
  if (!data) return null;

  const a = data.assessment;
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <p className="font-mono text-sm text-muted">{data.request_id}</p>
        <h1 className="text-3xl font-bold tracking-tight">Your repair</h1>
        <p className="mt-1 text-muted">
          {[data.address, data.community].filter(Boolean).join(", ")} · reported {when(data.lodged_at)}
        </p>
      </div>

      <Progress status={data.status} />

      {data.trip?.tenant_update && (
        <div role="status" className="flex items-start gap-3 rounded-2xl border border-routine/30 bg-routine-soft p-5">
          <Truck className="mt-0.5 size-6 shrink-0 text-routine" aria-hidden />
          <div>
            <p className="font-bold text-routine">A trip has been booked</p>
            <p className="text-lg">{data.trip.tenant_update}</p>
          </div>
        </div>
      )}

      {data.status === "awaiting_tenant" && data.question && <AnswerCard id={data.request_id} question={data.question} onDone={() => mutate()} />}

      {a && data.status !== "awaiting_tenant" && (
        <Docket requestId={data.request_id} tier={a.tier} explanation={a.explanation_tenant} address={data.address} community={data.community} />
      )}
    </div>
  );
}

const STAGES = [
  { key: "reported", label: "Reported" },
  { key: "assessed", label: "Assessed" },
  { key: "approved", label: "Checked by staff" },
  { key: "scheduled", label: "Trip booked" },
  { key: "completed", label: "Done" },
];

function Progress({ status }: { status: string }) {
  const reached =
    status === "completed" ? 4 : status === "scheduled" ? 3 : status === "approved" ? 2 : ["ranked", "not_in_queue", "needs_phone_call", "awaiting_confirmation"].includes(status) ? 1 : 0;
  return (
    <div className="rounded-2xl border border-line bg-paper p-5 shadow-sm">
      <p className="mb-4 flex items-center gap-2 font-bold">
        <CalendarClock className="size-5 text-ink" aria-hidden /> {statusLabel[status] ?? status}
      </p>
      <ol className="grid grid-cols-5 gap-2">
        {STAGES.map((s, i) => (
          <li key={s.key} className="flex flex-col gap-2">
            <span className={cx("h-2 rounded-full", i <= reached ? "bg-routine" : "bg-line")} aria-hidden />
            <span className={cx("flex items-center gap-1 text-sm", i <= reached ? "font-bold text-graphite" : "text-muted")}>
              {i <= reached && <CircleCheck className="size-4 text-routine" aria-hidden />}
              {s.label}
              <span className="sr-only">{i <= reached ? "(done)" : "(not yet)"}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function AnswerCard({ id, question, onDone }: { id: string; question: string; onDone: () => void }) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <form
      className="flex flex-col gap-4 rounded-2xl border-2 border-ink bg-paper p-5 shadow-sm sm:p-7"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await post(`/api/requests/${id}/clarify`, { answer: answer.trim() });
          onDone();
        } catch (err) {
          setError(err);
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2 className="text-xl font-bold">We need one answer before we can rank this</h2>
      <p className="text-2xl font-bold">{question}</p>
      <label htmlFor="answer" className="font-bold">Your answer</label>
      <input id="answer" value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={500} className={inputClass + " text-lg"} />
      {error != null && <ErrorBox error={error} />}
      <Button type="submit" busy={busy} disabled={!answer.trim()} className="self-start">
        Send answer <ArrowRight className="size-5" aria-hidden />
      </Button>
    </form>
  );
}
