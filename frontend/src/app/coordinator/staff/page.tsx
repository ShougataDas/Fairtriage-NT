"use client";

import { useState } from "react";
import useSWR from "swr";
import { UserPlus, Users } from "lucide-react";
import { fetcher, post } from "@/lib/api";
import { useMe, type User } from "@/lib/auth";
import { when } from "@/lib/format";
import { Button, Card, CardTitle, ErrorBox, Field, PageHeader, Pill, Spinner, inputClass } from "@/components/ui";

/** Administrators add, switch off and reset staff accounts. There is no public staff sign-up. */
export default function StaffAccountsPage() {
  const { user } = useMe();
  const { data, error, isLoading, mutate } = useSWR<User[]>(user?.role === "admin" ? "/api/staff/users" : null, fetcher);

  if (user && user.role !== "admin") {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Staff accounts" lede="Only an administrator can manage staff accounts." />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Staff accounts" lede="Add the people who use the staff area, switch off anyone who leaves, and reset passwords." />
      <AddStaff onAdded={() => mutate()} />
      <Card>
        <CardTitle icon={<Users className="size-5 text-ink" aria-hidden />}>Accounts</CardTitle>
        {isLoading && <Spinner label="Loading accounts" />}
        {error && <ErrorBox error={error} onRetry={() => mutate()} />}
        {data && (
          <ul className="divide-y divide-line">
            {data.map((u) => (
              <StaffRow key={u.id} u={u} self={u.id === user?.id} onChanged={() => mutate()} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function StaffRow({ u, self, onChanged }: { u: User; self: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [resetting, setResetting] = useState(false);
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>, done?: string) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      if (done) setMsg(done);
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-col gap-2 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <strong>{u.username}</strong>
        {u.name && <span className="text-muted">{u.name}</span>}
        <Pill tone={u.role === "admin" ? "ink" : "neutral"}>{u.role === "admin" ? "Administrator" : "Staff"}</Pill>
        {!u.active && <Pill tone="bad">Switched off</Pill>}
        {self && <Pill tone="good">You</Pill>}
        <span className="text-sm text-muted">added {u.created_at ? when(u.created_at) : ""}</span>
        <span className="ml-auto flex gap-2">
          {!self && (
            <Button variant="secondary" busy={busy} onClick={() => run(() => post(`/api/staff/users/${u.id}/active?active=${!u.active}`))}>
              {u.active ? "Switch off" : "Switch on"}
            </Button>
          )}
          <Button variant="secondary" onClick={() => { setResetting(!resetting); setMsg(null); }}>Reset password</Button>
        </span>
      </div>
      {resetting && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            run(() => post(`/api/staff/users/${u.id}/password`, { password: pw }), `New password set for ${u.username}.`).then(() => {
              setPw("");
              setResetting(false);
            });
          }}
        >
          <Field label="New password" hint="At least 8 characters" htmlFor={`pw-${u.id}`}>
            <input id={`pw-${u.id}`} type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" className={inputClass} />
          </Field>
          <Button type="submit" busy={busy} disabled={pw.length < 8}>Save</Button>
        </form>
      )}
      {msg && <p role="status" className="text-sm font-bold text-routine">{msg}</p>}
      {error != null && <ErrorBox error={error} />}
    </li>
  );
}

function AddStaff({ onAdded }: { onAdded: () => void }) {
  const [username, setUsername] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"staff" | "admin">("staff");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<string | null>(null);
  const ok = /^[A-Za-z0-9._-]{3,32}$/.test(username.trim()) && password.length >= 8;

  return (
    <Card>
      <CardTitle icon={<UserPlus className="size-5 text-ink" aria-hidden />}>Add a staff account</CardTitle>
      <form
        className="grid gap-4 sm:grid-cols-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!ok) return;
          setBusy(true);
          setError(null);
          setDone(null);
          try {
            const u = await post<User>("/api/staff/users", { username: username.trim(), name: name.trim(), password, role });
            setDone(`${u.username} can now sign in. Give them the password you set; they should keep it private.`);
            setUsername("");
            setName("");
            setPassword("");
            setRole("staff");
            onAdded();
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Username" hint="3 to 32 letters, numbers, dots or dashes" htmlFor="new-user">
          <input id="new-user" value={username} onChange={(e) => setUsername(e.target.value)} autoCapitalize="none" spellCheck={false} className={inputClass} />
        </Field>
        <Field label="Name" hint="Optional" htmlFor="new-name">
          <input id="new-name" value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
        </Field>
        <Field label="Password" hint="At least 8 characters" htmlFor="new-pw">
          <input id="new-pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" className={inputClass} />
        </Field>
        <Field label="Role" htmlFor="new-role">
          <select id="new-role" value={role} onChange={(e) => setRole(e.target.value as "staff" | "admin")} className={inputClass}>
            <option value="staff">Staff: queue, trips, fairness</option>
            <option value="admin">Administrator: also manages staff accounts</option>
          </select>
        </Field>
        <div className="flex flex-col gap-2 sm:col-span-2">
          {done && <p role="status" className="font-bold text-routine">{done}</p>}
          {error != null && <ErrorBox error={error} />}
          <Button type="submit" busy={busy} disabled={!ok} className="self-start">Add account</Button>
        </div>
      </form>
    </Card>
  );
}
