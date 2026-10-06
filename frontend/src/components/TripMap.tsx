"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useMemo } from "react";
import L from "leaflet";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { TripPlan } from "@/lib/api";
import { hoursOrDays } from "@/lib/format";

const TIER_HEX: Record<string, string> = { Immediate: "#b3261e", Urgent: "#9a5a00", Routine: "#2f6b4f" };
const INK = "#2b3a8f";

/** A round or square pin. `dx`/`dy` move it off its point in screen pixels, so
 *  several repairs in one community fan out around it at every zoom level. */
function pin(label: string, colour: string, shape: "circle" | "square" = "circle", dx = 0, dy = 0) {
  return L.divIcon({
    className: "",
    iconSize: [30, 30],
    iconAnchor: [15 - dx, 15 - dy],
    tooltipAnchor: [dx, dy - 14],
    html: `<div style="width:30px;height:30px;border-radius:${shape === "circle" ? "50%" : "8px"};background:${colour};
      color:#fff;display:grid;place-items:center;font:700 13px/1 system-ui;border:3px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.4)">${label}</div>`,
  });
}

/** The community itself, when it has several repairs: a small dot they fan out
 *  from. Its label sits to the right of the ring, clear of the pins. */
function hub(colour: string, labelDx: number) {
  return L.divIcon({
    className: "",
    iconSize: [12, 12],
    iconAnchor: [6, 6],
    tooltipAnchor: [labelDx, 0],
    html: `<div style="width:12px;height:12px;border-radius:50%;background:${colour};border:2px solid #fff;
      box-shadow:0 1px 3px rgba(0,0,0,.4)"></div>`,
  });
}

/** Screen offsets for n pins in a ring around their community; one pin sits on it. */
const ringRadius = (n: number) => (n <= 4 ? 26 : n <= 8 ? 34 : 42);

function ring(n: number): [number, number][] {
  if (n === 1) return [[0, 0]];
  const r = ringRadius(n);
  return Array.from({ length: n }, (_, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
    return [Math.round(r * Math.cos(a)), Math.round(r * Math.sin(a))];
  });
}

function Fit({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 1) map.setView(points[0], 9);
    else if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 10 });
  }, [map, points]);
  return null;
}

/** The recommended route, the alternatives it beat, and every stop in order. */
export default function TripMap({ trip }: { trip: TripPlan }) {
  const c = trip.coords;
  const chosen = trip.options.find((o) => o.chosen);

  const segments = useMemo(() => {
    // one polyline per leg, so charter legs can be dashed
    if (!chosen) return [];
    return chosen.nodes.slice(1).map((n, i) => ({
      from: chosen.nodes[i], to: n, air: chosen.modes[i] === "air",
    }));
  }, [chosen]);

  // every repair gets its own pin; repairs in the same community share its point
  const places = useMemo(() => {
    const out = new Map<string, TripPlan["stops"]>();
    for (const s of trip.stops) out.set(s.community, [...(out.get(s.community) ?? []), s]);
    return [...out.entries()].map(([community, stops]) => ({ community, stops }));
  }, [trip.stops]);

  const points = useMemo(
    () => [trip.start, ...trip.stops.map((s) => s.community), ...(chosen?.nodes ?? [])].filter((n) => c[n]).map((n) => c[n]),
    [trip, chosen, c],
  );

  if (!points.length) return null;
  const rank = (t: string) => ["Immediate", "Urgent", "Routine"].indexOf(t);

  return (
    <MapContainer center={points[0]} zoom={7} scrollWheelZoom={false} className="h-[380px] w-full rounded-2xl" attributionControl>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />
      <Fit points={points} />

      {trip.options.filter((o) => !o.chosen).map((o) => (
        <Polyline
          key={o.name}
          positions={o.nodes.filter((n) => c[n]).map((n) => c[n])}
          pathOptions={{ color: "#6b7280", weight: 3, opacity: 0.45, dashArray: "2 8" }}
        >
          <Tooltip sticky>Not chosen: {o.name} ({o.hours.toFixed(1)} h)</Tooltip>
        </Polyline>
      ))}

      {segments.map((sg, i) =>
        c[sg.from] && c[sg.to] ? (
          <Polyline
            key={i}
            positions={[c[sg.from], c[sg.to]]}
            pathOptions={{ color: INK, weight: 5, opacity: 0.9, dashArray: sg.air ? "10 10" : undefined }}
          >
            <Tooltip sticky>{sg.air ? "Charter flight" : "Road"}: {sg.from} → {sg.to}</Tooltip>
          </Polyline>
        ) : null,
      )}

      {c[trip.start] && (
        <Marker position={c[trip.start]} icon={pin("★", "#1f2329", "square")}>
          <Tooltip direction="top" offset={[0, -14]}>Crew starts: {trip.start}</Tooltip>
        </Marker>
      )}

      {places.map((p) => {
        if (!c[p.community]) return null;
        const worst = p.stops.reduce((w, s) => (rank(s.tier) < rank(w) ? s.tier : w), p.stops[0].tier);
        const dest = p.community === trip.community;
        const offsets = ring(p.stops.length);
        const many = p.stops.length > 1;
        return [
          many && (
            <Marker key={`${p.community}-hub`} position={c[p.community]} icon={hub(TIER_HEX[worst] ?? INK, ringRadius(p.stops.length) + 18)}>
              <Tooltip direction="right" permanent={dest}>
                <strong>{p.community}</strong>
                {dest ? " (destination)" : ""} · {p.stops.length} repairs
              </Tooltip>
            </Marker>
          ),
          ...p.stops.map((s, i) => {
            const [dx, dy] = offsets[i];
            const anchor = s.request_id === trip.anchor;
            return (
              <Marker
                key={s.request_id}
                position={c[p.community]}
                icon={pin(anchor ? "⚑" : String(s.order), TIER_HEX[s.tier] ?? INK, "circle", dx, dy)}
                zIndexOffset={anchor ? 1000 : 500 - i}
              >
                <Tooltip direction="top" permanent={!many && dest}>
                  <strong>
                    {anchor ? "Destination" : `Stop ${s.order}`} · {p.community}
                  </strong>
                  {s.address ? ` · ${s.address}` : ""}
                  <br />
                  {s.tier} · arrive {hoursOrDays(s.eta_hours, trip.workday_hours)}
                  <br />
                  <em>“{s.evidence.length > 60 ? `${s.evidence.slice(0, 60)}…` : s.evidence}”</em>
                </Tooltip>
              </Marker>
            );
          }),
        ];
      })}
    </MapContainer>
  );
}
