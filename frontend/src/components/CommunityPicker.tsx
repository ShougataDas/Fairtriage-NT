"use client";

import { useId, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { Check, ChevronDown, MapPin } from "lucide-react";
import { fetcher, type CommunityGroup } from "@/lib/api";
import { cx } from "@/lib/format";
import { inputClass } from "./ui";

/** Searchable place picker (ARIA combobox). 64 places is too many to scroll. */
export function CommunityPicker({
  value,
  onChange,
  id,
  invalid,
}: {
  value: string;
  onChange: (v: string) => void;
  id: string;
  invalid?: boolean;
}) {
  const { data: groups, error } = useSWR<CommunityGroup[]>("/api/communities", fetcher);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const flat = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out: { group: string; name: string; remote: boolean }[] = [];
    for (const g of groups ?? []) {
      for (const c of g.communities) {
        if (!q || c.name.toLowerCase().includes(q) || g.group.toLowerCase().includes(q)) out.push({ group: g.group, ...c });
      }
    }
    return out;
  }, [groups, query]);

  function choose(name: string) {
    onChange(name);
    setQuery("");
    setOpen(false);
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && open && flat[active]) {
      e.preventDefault();
      choose(flat[active].name);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  if (error) return <p className="text-immediate">Could not load the list of places. Is the FairTriage service running?</p>;

  return (
    <div className="relative">
      <div className="relative">
        <MapPin className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-muted" aria-hidden />
        <input
          ref={inputRef}
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-invalid={invalid || undefined}
          aria-activedescendant={open && flat[active] ? `${listId}-${active}` : undefined}
          autoComplete="off"
          placeholder={groups ? "Start typing: Wadeye, Palmerston, Katherine…" : "Loading places…"}
          className={cx(inputClass, "pl-11 pr-10", invalid && "border-immediate")}
          value={open ? query : value}
          onFocus={() => {
            setOpen(true);
            setQuery("");
            setActive(0);
          }}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onKeyDown={onKey}
        />
        <ChevronDown className="pointer-events-none absolute right-3.5 top-1/2 size-5 -translate-y-1/2 text-muted" aria-hidden />
      </div>
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-2 max-h-72 w-full overflow-auto rounded-xl border border-line bg-paper p-1 shadow-lg"
        >
          {flat.length === 0 && <li className="px-3 py-2 text-muted">No place matches “{query}”.</li>}
          {flat.map((c, i) => {
            const showGroup = i === 0 || flat[i - 1].group !== c.group;
            return (
              <li key={c.name} role="presentation">
                {showGroup && <div className="px-3 pb-1 pt-2 text-xs font-bold uppercase tracking-wide text-muted">{c.group}</div>}
                <div
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={c.name === value}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(c.name);
                  }}
                  onMouseEnter={() => setActive(i)}
                  className={cx(
                    "flex cursor-pointer items-center justify-between rounded-lg px-3 py-2",
                    i === active && "bg-ink-soft",
                  )}
                >
                  <span>{c.name}</span>
                  {c.name === value && <Check className="size-4 text-ink" aria-hidden />}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
