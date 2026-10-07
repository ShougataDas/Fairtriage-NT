"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { MessageSquare, Search } from "lucide-react";
import { post } from "@/lib/api";
import { Button, ErrorBox, Field, inputClass } from "@/components/ui";

export default function TrackPage() {
  const router = useRouter();
  const [ref, setRef] = useState("");
  const clean = ref.trim().toUpperCase();
  const valid = /^NTF3-\d{5}-[0-9A-F]{4}$/.test(clean);

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-3xl font-bold tracking-tight">Track a repair</h1>
      <p className="mt-2 text-lg text-muted">Enter the reference number you were given when you reported it.</p>
      <form
        className="mt-6 flex flex-col gap-4 rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-7"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) router.push(`/track/${clean.slice(0, 11)}${clean.slice(11).toLowerCase()}`);
        }}
      >
        <Field label="Reference number" hint="like NTF3-00012-ab34" htmlFor="ref">
          <input
            id="ref"
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="NTF3-00000-0000"
            className={inputClass + " font-mono text-lg"}
          />
        </Field>
        {ref && !valid && <p className="text-muted">A reference looks like NTF3, five digits, then four letters or numbers.</p>}
        <Button type="submit" disabled={!valid} className="self-start">
          <Search className="size-5" aria-hidden /> Find my repair
        </Button>
      </form>
      <LostReference />
    </div>
  );
}

/** A tenant who lost their reference gets it texted to the mobile they gave.
 *  The page never shows whether a number has repairs: same reply either way. */
function LostReference() {
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const mobile = phone.replace(/[\s().-]/g, "");
  const ok = /^(04\d{8}|\+?614\d{8}|4\d{8})$/.test(mobile);
  return (
    <form
      className="mt-6 flex flex-col gap-3 rounded-2xl border border-line bg-paper p-5 sm:p-7"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!ok) return;
        setBusy(true);
        setError(null);
        try {
          const r = await post<{ message: string }>("/api/sms/resend", { phone: phone.trim() });
          setReply(r.message);
        } catch (err) {
          setError(err);
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2 className="flex items-center gap-2 text-xl font-bold">
        <MessageSquare className="size-5 text-ink" aria-hidden /> Lost your reference number?
      </h2>
      {reply ? (
        <p role="status" className="font-bold text-routine">{reply}</p>
      ) : (
        <>
          <Field label="Your mobile number" hint="the one you gave when you reported the repair" htmlFor="lost-phone">
            <input
              id="lost-phone"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              maxLength={20}
              placeholder="0400 000 000"
              className={inputClass + " sm:max-w-xs"}
            />
          </Field>
          {phone && !ok && <p className="text-muted">Enter a mobile number starting 04.</p>}
          <Button type="submit" variant="secondary" busy={busy} disabled={!ok} className="self-start">
            <MessageSquare className="size-5" aria-hidden /> Text me my reference
          </Button>
        </>
      )}
      {error != null && <ErrorBox error={error} />}
    </form>
  );
}
