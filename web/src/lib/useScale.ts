"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useSyncExternalStore } from "react";
import { parseScale } from "./format";
import type { CommonScale, Scale } from "./types";

const KEY = "airatlas.commonScale";
const noopSubscribe = () => () => {};

function remembered(): CommonScale | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "eu_eaqi" || v === "who_2021_pm25" ? v : null;
  } catch {
    return null;
  }
}

/**
 * The scale lives in the URL (?scale=) so views are shareable. The last common scale someone picked is
 * remembered so the cross-region pages open on it.
 */
export function useScale(allowLocal: boolean): [Scale, (s: Scale) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const raw = params.get("scale");
  // Browser-only value: null during server render, so hydration never mismatches.
  const saved = useSyncExternalStore(noopSubscribe, remembered, () => null);
  const scale: Scale = allowLocal ? parseScale(raw, true) : raw ? parseScale(raw, false) : (saved ?? "eu_eaqi");

  const set = useCallback(
    (s: Scale) => {
      const next = new URLSearchParams(params.toString());
      if (s === "local") next.delete("scale");
      else {
        next.set("scale", s);
        try {
          localStorage.setItem(KEY, s);
        } catch {}
      }
      const q = next.toString();
      router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );
  return [scale, set];
}
