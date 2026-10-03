"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { House } from "lucide-react";
import { cx } from "@/lib/format";

/** Fired when a nav link for the page already open is clicked. Next.js does not
 * remount a page for a link to itself, so a page with steps (the report form)
 * listens and starts again, instead of the click appearing to do nothing. */
export const REOPEN_EVENT = "fairtriage:reopen";

const tenantLinks = [
  { href: "/report", label: "Report a repair" },
  { href: "/track", label: "Track a repair" },
];
const staffLinks = [
  { href: "/coordinator", label: "Queue" },
  { href: "/coordinator/trips", label: "Trips" },
  { href: "/coordinator/fairness", label: "Fairness" },
];

export function SiteHeader() {
  const path = usePathname();
  const staff = path.startsWith("/coordinator");
  const links = staff ? staffLinks : tenantLinks;
  const active = (href: string) =>
    href === "/coordinator" ? path === "/coordinator" || path.startsWith("/coordinator/requests") : path.startsWith(href);

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-paper/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-bold text-graphite">
          <span className="grid size-8 place-items-center rounded-lg bg-ink text-white">
            <House className="size-4" aria-hidden />
          </span>
          FairTriage NT
          {staff && <span className="rounded-md bg-ink-soft px-1.5 py-0.5 text-xs text-ink">Staff</span>}
        </Link>
        <nav aria-label="Main" className="flex flex-1 flex-wrap gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => {
                if (path === l.href) window.dispatchEvent(new CustomEvent(REOPEN_EVENT, { detail: l.href }));
              }}
              aria-current={active(l.href) ? "page" : undefined}
              className={cx(
                "rounded-lg px-3 py-2 font-bold transition",
                active(l.href) ? "bg-ink-soft text-ink" : "text-muted hover:bg-canvas hover:text-graphite",
              )}
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <Link href={staff ? "/report" : "/coordinator"} className="text-sm font-bold text-ink underline-offset-4 hover:underline">
          {staff ? "Tenant view" : "Staff area"}
        </Link>
      </div>
    </header>
  );
}
