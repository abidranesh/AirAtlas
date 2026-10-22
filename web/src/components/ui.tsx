import type { ReactNode } from "react";
import { KIND_LABELS, NO_DATA_COLOR, SCALE_LABELS, textOn } from "@/lib/format";
import type { Category, Freshness, Scale, StandardInfo, StationKind } from "@/lib/types";

export function AqiBadge({
  category,
  value,
  size = "md",
  showLabel = true,
}: {
  category: Category | null | undefined;
  value?: number | null;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}) {
  const bg = category?.color ?? NO_DATA_COLOR;
  const pad = { sm: "px-2 py-0.5 text-xs", md: "px-2.5 py-1 text-sm", lg: "px-4 py-2 text-lg" }[size];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold whitespace-nowrap ${pad}`}
      style={{ background: bg, color: textOn(bg) }}
    >
      {value !== undefined && value !== null && <span className="tabular-nums">{value}</span>}
      {showLabel && <span className="font-medium">{category?.label ?? "No data"}</span>}
    </span>
  );
}

const KIND_STYLE: Record<StationKind, string> = {
  reference: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  low_cost: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  modeled: "bg-neutral-200 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200",
};

export function KindBadge({ kind }: { kind: StationKind }) {
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${KIND_STYLE[kind]}`}>{KIND_LABELS[kind]}</span>;
}

export function FreshnessBadge({ freshness, age }: { freshness: Freshness; age: string }) {
  if (freshness === "fresh") return <span className="text-xs text-neutral-500">{age}</span>;
  const style =
    freshness === "stale"
      ? "bg-yellow-100 text-yellow-900 dark:bg-yellow-950 dark:text-yellow-200"
      : "bg-neutral-200 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300";
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs ${style}`}>
      {freshness === "stale" ? `Stale · ${age}` : "Data unavailable"}
    </span>
  );
}

export function ScaleToggle({
  value,
  options,
  onChange,
}: {
  value: Scale;
  options: Scale[];
  onChange: (s: Scale) => void;
}) {
  return (
    <div role="radiogroup" aria-label="AQI scale" className="inline-flex rounded-lg border border-neutral-300 p-0.5 dark:border-neutral-700">
      {options.map((o) => (
        <button
          key={o}
          role="radio"
          aria-checked={o === value}
          onClick={() => onChange(o)}
          className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
            o === value
              ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
              : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
          }`}
        >
          {SCALE_LABELS[o]}
        </button>
      ))}
    </div>
  );
}

export function Legend({ standard }: { standard: StandardInfo }) {
  return (
    <div>
      <p className="mb-1.5 text-xs text-neutral-500">{standard.name}</p>
      <ul className="flex flex-wrap gap-1.5">
        {standard.categories.map((c) => (
          <li key={c.key} className="rounded px-2 py-0.5 text-xs font-medium" style={{ background: c.color, color: textOn(c.color) }}>
            {c.label}
            {c.index_range ? ` ${c.index_range[0]}–${c.index_range[1]}` : ""}
          </li>
        ))}
        <li className="rounded px-2 py-0.5 text-xs font-medium" style={{ background: NO_DATA_COLOR, color: textOn(NO_DATA_COLOR) }}>
          No data
        </li>
      </ul>
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900 ${className}`}>
      {children}
    </section>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-neutral-200 dark:bg-neutral-800 ${className}`} />;
}

export function ErrorNote({ error }: { error: Error }) {
  return (
    <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900 dark:bg-red-950 dark:text-red-200">
      Could not load data: {error.message}
    </p>
  );
}
