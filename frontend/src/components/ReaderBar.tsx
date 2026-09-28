"use client";

import useSWR from "swr";
import { TriangleAlert } from "lucide-react";
import { fetcher, type Health } from "@/lib/api";

/** Silent while everything works. Speaks up only when staff would otherwise
 *  be looking at stale or missing data: the service or its database is down,
 *  or a switched-on model has stopped answering. */
export function ReaderBar() {
  const { data, error } = useSWR<Health>("/api/health", fetcher, { refreshInterval: 30000 });

  let message: string | null = null;
  if (error) message = "The FairTriage service is not reachable. Start it, then refresh.";
  else if (data?.database === "unreachable") message = "The database (MongoDB) is not reachable. New reports cannot be saved.";
  else if (data && !data.reader.ok) message = data.reader.label;

  if (!message) return null;
  return (
    <div role="alert" className="mb-6 flex items-start gap-2 rounded-xl border border-immediate/30 bg-immediate-soft px-4 py-3 text-immediate">
      <TriangleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
      <span className="font-bold">{message}</span>
    </div>
  );
}
