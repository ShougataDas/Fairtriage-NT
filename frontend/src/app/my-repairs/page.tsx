"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { ChevronRight, ClipboardList, Plus } from "lucide-react";
import { fetcher, post, type Tier } from "@/lib/api";
import { statusLabel, when } from "@/lib/format";
import { Button, ButtonLink, Empty, ErrorBox, Field, Spinner, TierBadge, inputClass } from "@/components/ui";

interface MyRepair {
  request_id: string;
  status: string;
  lodged_at: string;
  community: string;
  address: string | null;
  text: string;
  tier: Tier | null;
}

/** A signed-in tenant's repairs, newest first. */
export default function MyRepairsPage() {
  const { data, error, isLoading, mutate } = useSWR<MyRepair[]>("/api/me/requests", fetcher);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">My repairs</h1>
          <p className="mt-1 text-muted">Every repair on your account. Open one to see its progress and ask why it is where it is.</p>
        </div>
        <ButtonLink href="/report">Report a repair</ButtonLink>
      </div>

      {isLoading && <Spinner label="Loading your repairs" />}
      {error && <ErrorBox error={error} onRetry={() => mutate()} />}
      {data && data.length === 0 && (
        <Empty icon={<ClipboardList className="size-8" aria-hidden />} title="No repairs on your account yet">
          Repairs you report while signed in appear here. A repair you reported before signing in can be added below.
        </Empty>
      )}
      {data && data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {data.map((r) => (
            <li key={r.request_id}>
              <Link href={`/track/${r.request_id}`} className="flex items-center gap-4 rounded-2xl border border-line bg-paper p-4 shadow-sm hover:border-ink/50">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {r.tier && r.tier !== "NotInQueue" && <TierBadge tier={r.tier} size="sm" />}
                    <span className="font-mono text-sm text-muted">{r.request_id}</span>
                    <span className="text-sm font-bold">{statusLabel[r.status] ?? r.status}</span>
                  </div>
                  <p className="mt-1 truncate italic">“{r.text}”</p>
                  <p className="text-sm text-muted">{[r.address, r.community].filter(Boolean).join(", ")} · reported {when(r.lodged_at)}</p>
                </div>
                <ChevronRight className="size-5 shrink-0 text-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
      <AddEarlier onAdded={() => mutate()} />
    </div>
  );
}

function AddEarlier({ onAdded }: { onAdded: () => void }) {
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<string | null>(null);
  const valid = /^NTF3-\d{5}-[0-9A-Fa-f]{4}$/.test(ref.trim());

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (!valid) return;
        setBusy(true);
        setError(null);
        setDone(null);
        try {
          const r = await post<{ request_id: string }>("/api/me/claim", { reference: ref.trim() });
          setDone(`${r.request_id} has been added to your account.`);
          setRef("");
          onAdded();
        } catch (err) {
          setError(err);
        } finally {
          setBusy(false);
        }
      }}
      className="flex flex-col gap-3 rounded-2xl border border-line bg-paper p-5"
    >
      <h2 className="flex items-center gap-2 text-lg font-bold"><Plus className="size-5 text-ink" aria-hidden /> Add a repair you reported before</h2>
      <p className="text-sm text-muted">Enter its reference number. It must have been reported with the same mobile number as your account.</p>
      <Field label="Reference number" htmlFor="claim-ref">
        <input id="claim-ref" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="NTF3-00000-0000"
          spellCheck={false} className={inputClass + " font-mono sm:max-w-xs"} />
      </Field>
      {done && <p role="status" className="font-bold text-routine">{done}</p>}
      {error != null && <ErrorBox error={error} />}
      <Button type="submit" variant="secondary" busy={busy} disabled={!valid} className="self-start">Add to my account</Button>
    </form>
  );
}
