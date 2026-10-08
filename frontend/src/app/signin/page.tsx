"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { KeyRound, LogIn, UserPlus } from "lucide-react";
import { register, safeNext, signIn } from "@/lib/auth";
import { cx, mobileProblem } from "@/lib/format";
import { Button, ErrorBox, Field, Spinner, inputClass } from "@/components/ui";

export default function SignInPage() {
  return (
    <Suspense fallback={<Spinner label="Loading" />}>
      <SignIn />
    </Suspense>
  );
}

type Tab = "tenant" | "staff";

function SignIn() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>(params.get("as") === "staff" ? "staff" : "tenant");
  const next = params.get("next");

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Sign in</h1>
        <p className="mt-2 text-muted">
          {tab === "tenant"
            ? "Tenants: see all your repairs in one place. You can still report or track a repair without an account."
            : "Maintenance staff: the queue, trips and fairness tools."}
        </p>
      </div>
      <div role="tablist" aria-label="Who are you" className="grid grid-cols-2 rounded-xl border border-line p-1">
        {(["tenant", "staff"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cx("rounded-lg px-3 py-2 font-bold", tab === t ? "bg-ink text-white" : "text-muted hover:text-graphite")}
          >
            {t === "tenant" ? "Tenant" : "Staff"}
          </button>
        ))}
      </div>
      {tab === "tenant" ? <TenantForms next={next} /> : <StaffForm next={next} />}
    </div>
  );
}

function TenantForms({ next }: { next: string | null }) {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "create">("signin");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [touched, setTouched] = useState(false);

  const phoneProblem = mobileProblem(phone);
  const pwProblem = mode === "create" && password.length < 8 ? "Use at least 8 characters." : null;
  const confirmProblem = mode === "create" && confirm !== password ? "The two passwords are different." : null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (phoneProblem || pwProblem || confirmProblem || !password) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "create") await register(phone.trim(), password, name.trim());
      else await signIn("tenant", phone.trim(), password);
      router.replace(safeNext(next, "/my-repairs"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-7">
      <h2 className="flex items-center gap-2 text-xl font-bold">
        {mode === "create" ? <UserPlus className="size-5 text-ink" aria-hidden /> : <LogIn className="size-5 text-ink" aria-hidden />}
        {mode === "create" ? "Create a tenant account" : "Tenant sign in"}
      </h2>
      {mode === "create" && (
        <Field label="Your name" hint="Optional" htmlFor="name">
          <input id="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoComplete="name" className={inputClass} />
        </Field>
      )}
      <Field label="Mobile number" htmlFor="t-phone">
        <input id="t-phone" type="tel" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
          maxLength={20} placeholder="0400 000 000" className={inputClass} />
      </Field>
      {touched && phoneProblem && <p className="text-immediate">{phoneProblem}</p>}
      <Field label="Password" hint={mode === "create" ? "At least 8 characters" : undefined} htmlFor="t-pw">
        <input id="t-pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === "create" ? "new-password" : "current-password"} className={inputClass} />
      </Field>
      {touched && pwProblem && <p className="text-immediate">{pwProblem}</p>}
      {mode === "create" && (
        <>
          <Field label="Type the password again" htmlFor="t-pw2">
            <input id="t-pw2" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" className={inputClass} />
          </Field>
          {touched && confirmProblem && <p className="text-immediate">{confirmProblem}</p>}
        </>
      )}
      {error != null && <ErrorBox error={error} />}
      <Button type="submit" busy={busy} className="self-start">
        {mode === "create" ? "Create account" : "Sign in"}
      </Button>
      <p className="text-sm text-muted">
        {mode === "create" ? "Already have an account? " : "No account yet? "}
        <button
          type="button"
          onClick={() => {
            setMode(mode === "create" ? "signin" : "create");
            setError(null);
            setTouched(false);
          }}
          className="font-bold text-ink underline"
        >
          {mode === "create" ? "Sign in" : "Create one"}
        </button>
      </p>
    </form>
  );
}

function StaffForm({ next }: { next: string | null }) {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (!username.trim() || !password) return;
        setBusy(true);
        setError(null);
        try {
          await signIn("staff", username.trim(), password);
          const dest = safeNext(next, "/coordinator");
          router.replace(dest.startsWith("/coordinator") ? dest : "/coordinator");
        } catch (err) {
          setError(err);
        } finally {
          setBusy(false);
        }
      }}
      className="flex flex-col gap-4 rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-7"
    >
      <h2 className="flex items-center gap-2 text-xl font-bold">
        <KeyRound className="size-5 text-ink" aria-hidden /> Staff sign in
      </h2>
      <Field label="Username" htmlFor="s-user">
        <input id="s-user" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
          autoCapitalize="none" spellCheck={false} className={inputClass} />
      </Field>
      <Field label="Password" htmlFor="s-pw">
        <input id="s-pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" className={inputClass} />
      </Field>
      {error != null && <ErrorBox error={error} />}
      <Button type="submit" busy={busy} disabled={!username.trim() || !password} className="self-start">
        Sign in
      </Button>
      <p className="text-sm text-muted">Staff accounts are created by an administrator. There is no public staff sign-up.</p>
    </form>
  );
}
