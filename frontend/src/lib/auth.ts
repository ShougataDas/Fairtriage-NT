"use client";

import useSWR, { mutate } from "swr";
import { fetcher, post } from "@/lib/api";

export type Role = "tenant" | "staff" | "admin";

export interface User {
  id: string;
  role: Role;
  name: string;
  username: string | null;
  phone: string | null;
  active: boolean;
  created_at: string | null;
}

const ME = "/api/auth/me";

/** Who is signed in. `user` is null when signed out; undefined while loading. */
export function useMe() {
  const { data, isLoading } = useSWR<{ user: User | null }>(ME, fetcher, { revalidateOnFocus: true });
  return { user: data?.user, loading: isLoading && !data };
}

export const isStaff = (u: User | null | undefined) => !!u && (u.role === "staff" || u.role === "admin");

export async function signIn(kind: "tenant" | "staff", identifier: string, password: string) {
  const r = await post<{ user: User }>("/api/auth/signin", { kind, identifier, password });
  await mutate(ME, { user: r.user }, { revalidate: false });
  return r.user;
}

export async function register(phone: string, password: string, name: string) {
  const r = await post<{ user: User }>("/api/auth/register", { phone, password, name });
  await mutate(ME, { user: r.user }, { revalidate: false });
  return r.user;
}

export async function signOut() {
  await post("/api/auth/signout");
  await mutate(() => true, undefined, { revalidate: false });      // forget everything cached
  await mutate(ME, { user: null }, { revalidate: false });
}

/** Only a path inside this site, so a crafted ?next= link cannot send anyone elsewhere. */
export function safeNext(next: string | null | undefined, fallback: string): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || !/^\/[A-Za-z0-9/_\-?=&.]*$/.test(next)) return fallback;
  return next;
}
