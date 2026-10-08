"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { isStaff, useMe } from "@/lib/auth";
import { Spinner } from "@/components/ui";

/**
 * Keeps each role in its own part of the site:
 *   - the staff area (/coordinator...) needs a staff sign-in; anyone else is
 *     sent to the staff sign-in page,
 *   - staff see only the staff area: tenant pages send them to the queue,
 *   - My repairs needs a tenant sign-in.
 * This is the screen-level guard. The server checks every staff request on its
 * own, so no staff data reaches a browser without a staff session.
 */
export function RoleGate({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const { user, loading } = useMe();

  const staffArea = path.startsWith("/coordinator");
  const signinPage = path.startsWith("/signin");
  const tenantOnly = path.startsWith("/my-repairs");

  const target = loading
    ? null
    : staffArea && !isStaff(user)
      ? `/signin?as=staff&next=${encodeURIComponent(path)}`
      : !staffArea && !signinPage && isStaff(user)
        ? "/coordinator"
        : tenantOnly && user?.role !== "tenant"
          ? `/signin?next=${encodeURIComponent(path)}`
          : null;

  useEffect(() => {
    if (target) router.replace(target);
  }, [target, router]);

  if ((loading && (staffArea || tenantOnly)) || target) return <Spinner label="Checking your sign-in" />;
  return <>{children}</>;
}
