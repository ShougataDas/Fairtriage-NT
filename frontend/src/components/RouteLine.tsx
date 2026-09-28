import { Flag, Plane, Truck } from "lucide-react";
import type { TripPlan } from "@/lib/api";
import { cx, hoursOrDays, tierStyle } from "@/lib/format";

/** Crew start → stops → destination, with the expected arrival at each place.
 *  Horizontal on wide screens, vertical on phones. */
export function RouteLine({ trip }: { trip: TripPlan }) {
  // group consecutive stops in the same community
  const places: { community: string; stops: TripPlan["stops"]; dest: boolean }[] = [];
  for (const s of trip.stops) {
    const last = places[places.length - 1];
    if (last && last.community === s.community) last.stops.push(s);
    else places.push({ community: s.community, stops: [s], dest: s.community === trip.community });
  }
  const air = trip.route?.by_air;

  return (
    <ol className="flex flex-col gap-0 md:flex-row md:items-start" aria-label="Trip route">
      <Node icon={<Truck className="size-4" aria-hidden />} tone="bg-graphite text-white" title={trip.start} sub={trip.start_offset_h > 0 ? `leaves in ${hoursOrDays(trip.start_offset_h, trip.workday_hours)}` : "crew is here"} first air={air} />
      {places.map((p, i) => {
        const first = p.stops[0];
        const worst = p.stops.reduce((w, s) => (["Immediate", "Urgent", "Routine"].indexOf(s.tier) < ["Immediate", "Urgent", "Routine"].indexOf(w) ? s.tier : w), p.stops[0].tier);
        return (
          <Node
            key={p.community + i}
            icon={p.dest ? <Flag className="size-4" aria-hidden /> : <span className="text-xs font-bold">{i + 1}</span>}
            tone={cx(tierStyle[worst].dot, "text-white")}
            title={p.community}
            sub={`arrive ${hoursOrDays(first.eta_hours, trip.workday_hours)}`}
            extra={`${p.stops.length} job${p.stops.length > 1 ? "s" : ""}${p.dest ? " · destination" : ""}`}
            last={i === places.length - 1}
            air={air}
          />
        );
      })}
    </ol>
  );
}

function Node({
  icon, tone, title, sub, extra, first, last, air,
}: { icon: React.ReactNode; tone: string; title: string; sub: string; extra?: string; first?: boolean; last?: boolean; air?: boolean }) {
  return (
    <li className="relative flex gap-3 pb-5 md:flex-1 md:flex-col md:items-center md:gap-2 md:pb-0 md:text-center">
      {!last && (
        <span
          aria-hidden
          className={cx(
            "absolute left-[15px] top-8 h-[calc(100%-2rem)] w-0.5 md:left-1/2 md:top-[15px] md:h-0.5 md:w-full",
            air && first ? "border-l-2 border-dashed border-ink md:border-l-0 md:border-t-2" : "bg-ink/40",
          )}
        />
      )}
      {air && first && !last && (
        <Plane aria-hidden className="absolute left-[7px] top-10 size-4 rotate-90 bg-paper text-ink md:left-[calc(100%-8px)] md:top-[7px] md:rotate-0" />
      )}
      <span className={cx("relative z-10 grid size-8 shrink-0 place-items-center rounded-full ring-4 ring-paper", tone)}>{icon}</span>
      <span className="flex flex-col md:items-center">
        <span className="font-bold leading-tight">{title}</span>
        <span className="text-sm text-muted">{sub}</span>
        {extra && <span className="text-xs text-muted">{extra}</span>}
      </span>
    </li>
  );
}
