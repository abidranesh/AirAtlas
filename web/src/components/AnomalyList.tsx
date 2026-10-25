import Link from "next/link";
import { hintInfo } from "@/lib/anomaly";
import { fmt, localTime, POLLUTANTS } from "@/lib/format";
import type { AnomalyEpisode, AnomalyHint } from "@/lib/types";

const CONFIDENCE_STYLE = {
  high: "font-semibold",
  medium: "",
  low: "opacity-70",
} as const;

export function HintChip({ hint }: { hint: AnomalyHint }) {
  const info = hintInfo(hint.kind);
  return (
    <span
      title={`${hint.text} (${hint.confidence} confidence)`}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${CONFIDENCE_STYLE[hint.confidence]}`}
      style={{ borderColor: info.color }}
    >
      <span aria-hidden>{info.icon}</span>
      {info.label}
      <span className="sr-only"> ({hint.confidence} confidence)</span>
    </span>
  );
}

export function EpisodeItem({ ep, tz, showStation = true }: { ep: AnomalyEpisode; tz: string; showStation?: boolean }) {
  const p = POLLUTANTS[ep.pollutant];
  return (
    <li className="space-y-1 py-2">
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
        {showStation && (
          <Link href={`/station/${ep.station_id}`} className="font-medium hover:underline">
            {ep.station}
          </Link>
        )}
        <span>
          {p?.label ?? ep.pollutant} peaked at <strong className="tabular-nums">{fmt(ep.peak, 0)}</strong> {p?.unit}
          {ep.details.ratio ? ` (${fmt(ep.details.ratio)}× usual)` : ""}
        </span>
        <span className="text-xs text-neutral-500">
          {localTime(ep.peak_at, tz)} · {ep.details.hours} h
        </span>
      </div>
      {ep.hints.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {ep.hints.map((h) => (
            <HintChip key={h.kind} hint={h} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-neutral-500">No clear cause in the available evidence.</p>
      )}
      {ep.hints[0] && <p className="text-xs text-neutral-600 dark:text-neutral-400">{ep.hints[0].text}</p>}
    </li>
  );
}
