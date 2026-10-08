"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, House, MessageCircleQuestion, Send, Siren } from "lucide-react";
import { post, type LodgeResult, type Tier } from "@/lib/api";
import { cx, mobileProblem } from "@/lib/format";
import { CommunityPicker } from "@/components/CommunityPicker";
import { Docket } from "@/components/Docket";
import { SmsNote } from "@/components/SmsNote";
import { REOPEN_EVENT } from "@/components/SiteHeader";
import { useMe } from "@/lib/auth";
import { Button, ButtonLink, ErrorBox, Field, inputClass } from "@/components/ui";

const EXAMPLES = [
  "power point is sparking",
  "toilet blocked, water on the floor",
  "no hot water since friday",
  "back door won't lock",
  "aircon broken, kids in the house",
];

const HOUSEHOLD = [
  { value: "children", label: "Children" },
  { value: "elderly", label: "Older person" },
  { value: "disability", label: "Person with disability" },
  { value: "medical_equipment", label: "Medical equipment" },
];

type Step = "describe" | "question" | "done";

export default function ReportPage() {
  const [step, setStep] = useState<Step>("describe");
  const [text, setText] = useState("");
  const [community, setCommunity] = useState("");
  const [address, setAddress] = useState("");
  const [phone, setPhone] = useState("");
  // a signed-in tenant's mobile is filled in; the repair goes on their account
  const { user } = useMe();
  useEffect(() => {
    if (user?.role === "tenant" && user.phone && !phone) setPhone("0" + user.phone.slice(3));
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  const [household, setHousehold] = useState<string[]>([]);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<LodgeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);
  const top = useRef<HTMLDivElement>(null);

  const missingText = !text.trim();
  const missingPlace = !community;
  const missingAddress = address.trim().length < 3;
  // an Australian mobile: texts only reach mobiles (04..., +61 4...)
  const phoneProblem = mobileProblem(phone);
  const badPhone = phoneProblem !== null;

  async function lodge(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (missingText || missingPlace || missingAddress || badPhone) return;
    setBusy(true);
    setError(null);
    try {
      const r = await post<LodgeResult>("/api/requests", {
        text: text.trim(), community, address: address.trim(), phone: phone.trim(), vulnerability: household,
      });
      setResult(r);
      setStep(r.status === "awaiting_tenant" ? "question" : "done");
      top.current?.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function sendAnswer(e: React.FormEvent) {
    e.preventDefault();
    if (!result || !answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await post<LodgeResult>(`/api/requests/${result.request_id}/clarify`, { answer: answer.trim() });
      setResult(r);
      setStep("done");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setStep("describe");
    setText("");
    setAnswer("");
    setResult(null);
    setError(null);
    setTouched(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // "Report a repair" in the header, clicked while already here: a new report
  useEffect(() => {
    const onReopen = (e: Event) => {
      if ((e as CustomEvent<string>).detail === "/report") reset();
    };
    window.addEventListener(REOPEN_EVENT, onReopen);
    return () => window.removeEventListener(REOPEN_EVENT, onReopen);
  }, []);

  return (
    <div ref={top} className="mx-auto flex max-w-2xl scroll-mt-24 flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Report a repair</h1>
        <Steps step={step} />
      </div>

      {step === "describe" && (
        <>
          <div role="note" className="flex items-start gap-3 rounded-xl border border-immediate/30 bg-immediate-soft p-4 text-immediate">
            <Siren className="mt-0.5 size-5 shrink-0" aria-hidden />
            <p className="font-bold">Fire, or someone hurt? Call 000 now.</p>
          </div>

          <form onSubmit={lodge} noValidate className="flex flex-col gap-6 rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-7">
            <Field label="What is wrong?" hint="In your own words. Short is fine." htmlFor="text">
              <textarea
                id="text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={2000}
                rows={5}
                aria-invalid={touched && missingText ? true : undefined}
                aria-describedby="text-help"
                placeholder="for example: toilet blocked, water on the floor"
                className={cx(inputClass, "resize-y text-lg", touched && missingText && "border-immediate")}
              />
              <div id="text-help" className="flex flex-wrap items-center gap-2 text-sm text-muted">
                <span>Examples:</span>
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    onClick={() => setText(ex)}
                    className="rounded-full border border-line px-3 py-1 hover:border-ink hover:text-ink"
                  >
                    {ex}
                  </button>
                ))}
              </div>
              {touched && missingText && <p className="text-immediate">Write a few words about what is wrong.</p>}
            </Field>

            <fieldset className="flex flex-col gap-4 rounded-2xl bg-canvas p-4 sm:p-5">
              <legend className="sr-only">Your address</legend>
              <p className="flex items-center gap-2 font-bold"><House className="size-5 text-ink" aria-hidden /> Where is the house?</p>
              <Field label="Street address" hint="House or unit number and street, or lot number" htmlFor="address">
                <input
                  id="address"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  maxLength={200}
                  autoComplete="street-address"
                  placeholder="for example: Unit 4, 12 Smith Street  or  Lot 231"
                  aria-invalid={touched && missingAddress ? true : undefined}
                  className={cx(inputClass, touched && missingAddress && "border-immediate")}
                />
                {touched && missingAddress && <p className="text-immediate">Write the house or unit number and street, or the lot number.</p>}
              </Field>
              <Field label="Suburb or community" htmlFor="community">
                <CommunityPicker id="community" value={community} onChange={setCommunity} invalid={touched && missingPlace} />
                {touched && missingPlace && <p className="text-immediate">Choose your suburb or community.</p>}
              </Field>
              <Field label="Mobile number" hint="Required. We text you your reference number and the message you see here, so you can always check on your repair." htmlFor="phone">
                <input
                  id="phone"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  maxLength={20}
                  placeholder="0400 000 000"
                  aria-invalid={touched && badPhone ? true : undefined}
                  className={cx(inputClass, "sm:max-w-xs", touched && badPhone && "border-immediate")}
                />
                {touched && badPhone && (
                  <p className="text-immediate">
                    {phoneProblem}
                  </p>
                )}
              </Field>
            </fieldset>

            <fieldset className="flex flex-col gap-2">
              <legend className="font-bold">
                Who lives in the house? <span className="font-normal text-muted">Optional.</span>
              </legend>
              <div className="flex flex-wrap gap-2">
                {HOUSEHOLD.map((h) => {
                  const on = household.includes(h.value);
                  return (
                    <label
                      key={h.value}
                      className={cx(
                        "flex cursor-pointer items-center gap-2 rounded-full border px-4 py-2 transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ink",
                        on ? "border-ink bg-ink-soft font-bold text-ink" : "border-line hover:border-ink",
                      )}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={on}
                        onChange={() => setHousehold(on ? household.filter((x) => x !== h.value) : [...household, h.value])}
                      />
                      {h.label}
                    </label>
                  );
                })}
              </div>
              <p className="text-sm text-muted">This can move your repair up within its group. Staff may check it against your tenancy record.</p>
            </fieldset>

            {error != null && <ErrorBox error={error} />}
            <Button type="submit" busy={busy} className="self-start text-lg">
              <Send className="size-5" aria-hidden /> {busy ? "Reading your report…" : "Send report"}
            </Button>
            <SlowNote busy={busy} />
          </form>
        </>
      )}

      {step === "question" && result?.question && (
        <form onSubmit={sendAnswer} className="flex flex-col gap-5 rounded-2xl border-2 border-ink bg-paper p-5 shadow-sm sm:p-7">
          <div className="flex items-start gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-ink-soft text-ink">
              <MessageCircleQuestion className="size-6" aria-hidden />
            </span>
            <div>
              <h2 className="text-xl font-bold">One question before we rank this</h2>
              <p className="text-muted">The answer changes how urgent it is, so we ask rather than guess.</p>
            </div>
          </div>
          <p className="text-2xl font-bold">{result.question}</p>
          <QuickAnswers question={result.question} onPick={setAnswer} />
          <Field label="Your answer" htmlFor="answer">
            <input id="answer" autoFocus value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={500} className={cx(inputClass, "text-lg")} />
          </Field>
          {error != null && <ErrorBox error={error} />}
          <Button type="submit" busy={busy} disabled={!answer.trim()} className="self-start text-lg">
            Send answer <ArrowRight className="size-5" aria-hidden />
          </Button>
          <SlowNote busy={busy} />
          <p className="text-sm text-muted">
            Your report is saved as <strong className="font-mono">{result.request_id}</strong>.
          </p>
          <SmsNote sms={result.sms} reference={result.request_id} />
        </form>
      )}

      {step === "done" && result?.explanation_tenant && result.tier && (
        <div className="flex flex-col gap-4">
          <Docket requestId={result.request_id} tier={result.tier as Tier} explanation={result.explanation_tenant} address={address} community={community} />
          <SmsNote sms={result.sms} reference={result.request_id} />
          <div className="flex flex-wrap gap-3">
            <ButtonLink href={`/track/${result.request_id}`}>Open this record</ButtonLink>
            <Button variant="secondary" onClick={reset}>Report something else</Button>
          </div>
          <p className="text-muted">
            Keep your reference number. You can check on your repair any time from{" "}
            <Link className="font-bold text-ink underline" href="/track">Track a repair</Link>.
          </p>
        </div>
      )}
    </div>
  );
}

function Steps({ step }: { step: Step }) {
  const items: [Step, string][] = [["describe", "Describe"], ["question", "Check"], ["done", "Result"]];
  const idx = items.findIndex(([s]) => s === step);
  return (
    <ol className="mt-4 flex items-center gap-1.5 text-sm sm:gap-2" aria-label="Progress">
      {items.map(([s, label], i) => (
        <li key={s} className="flex items-center gap-2" aria-current={i === idx ? "step" : undefined}>
          <span
            className={cx(
              "grid size-7 place-items-center rounded-full font-bold",
              i < idx && "bg-routine text-white",
              i === idx && "bg-ink text-white",
              i > idx && "bg-line text-muted",
            )}
          >
            {i + 1}
          </span>
          <span className={cx(i === idx ? "font-bold text-graphite" : "text-muted")}>{label}</span>
          {i < items.length - 1 && <span className="h-px w-3 bg-line sm:mx-1 sm:w-8" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

function QuickAnswers({ question, onPick }: { question: string; onPick: (a: string) => void }) {
  const q = question.toLowerCase();
  const options = q.includes("only toilet")
    ? ["Yes, it is the only one", "No, there is another"]
    : q.includes("lock")
      ? ["Yes, it locks", "No, we cannot lock it"]
      : q.includes("near any light")
        ? ["Yes, near power", "No, not near anything electrical"]
        : q.includes("whole house")
          ? ["The whole house", "Just one room"]
          : [];
  if (!options.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button key={o} type="button" onClick={() => onPick(o)} className="rounded-xl border-2 border-line px-4 py-2 font-bold hover:border-ink hover:text-ink">
          {o}
        </button>
      ))}
    </div>
  );
}

/** Reading a message can take a while when a model is busy. Say so, rather
 *  than leave someone with a spinner and no idea whether it worked. */
function SlowNote({ busy }: { busy: boolean }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!busy) {
      setSlow(false);
      return;
    }
    const t = setTimeout(() => setSlow(true), 4000);
    return () => clearTimeout(t);
  }, [busy]);
  if (!slow) return null;
  return (
    <p role="status" className="text-muted">
      Still working. This can take up to half a minute. Your report is not lost; please keep this page open.
    </p>
  );
}
