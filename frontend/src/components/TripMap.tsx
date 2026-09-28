"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useMemo } from "react";
import L from "leaflet";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { TripPlan } from "@/lib/api";
import { hoursOrDays } from "@/lib/format";

const TIER_HEX: Record<string, string> = { Immediate: "#b3261e", Urgent: "#9a5a00", Routine: "#2f6b4f" };
const INK = "#2b3a8f";

function pin(label: string, colour: string, shape: "circle" | "square" = "circle") {
  return L.divIcon({
    className: "",
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<div style="width:30px;height:30px;border-radius:${shape === "circle" ? "50%" : "8px"};background:${colour};
      color:#fff;display:grid;place-items:center;font:700 13px/1 system-ui;border:3px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.4)">${label}</div>`,
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

  const places = useMemo(() => {
    const out: { community: string; order: number; stops: TripPlan["stops"] }[] = [];
    for (const s of trip.stops) {
      const last = out[out.length - 1];
      if (last && last.community === s.community) last.stops.push(s);
      else out.push({ community: s.community, order: out.length + 1, stops: [s] });
    }
    return out;
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
        const worst = p.stops.reduce((w, s) => (rank(s.tier) < rank(w) ? s.tier : w), p.stops[0].tier);
        const dest = p.community === trip.community;
        return c[p.community] ? (
          <Marker key={p.community} position={c[p.community]} icon={pin(dest ? "⚑" : String(p.order), TIER_HEX[worst] ?? INK)}>
            <Tooltip direction="top" offset={[0, -14]} permanent={dest}>
              <strong>{p.community}</strong>
              {dest ? " (destination)" : ""}
              <br />
              {p.stops.length} job{p.stops.length > 1 ? "s" : ""} · arrive {hoursOrDays(p.stops[0].eta_hours, trip.workday_hours)}
            </Tooltip>
          </Marker>
        ) : null;
      })}
    </MapContainer>
  );
}
