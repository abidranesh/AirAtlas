"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { useApi } from "@/lib/api";
import { REGION_NAMES } from "@/lib/format";
import type { SearchResult } from "@/lib/types";

export default function SearchBox() {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const listId = useId();

  useEffect(() => {
    const t = setTimeout(() => setQuery(text.trim()), 250); // debounce typing
    return () => clearTimeout(t);
  }, [text]);

  const { data, loading } = useApi<{ results: SearchResult[] }>(query.length >= 2 ? `/search?q=${encodeURIComponent(query)}` : null);
  const results = query.length >= 2 ? data?.results ?? [] : [];

  return (
    <div className="relative w-full max-w-md">
      <label htmlFor={`${listId}-input`} className="sr-only">
        Search a station, city or district
      </label>
      <input
        id={`${listId}-input`}
        type="search"
        role="combobox"
        aria-autocomplete="list"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Search a station, city or district…"
        autoComplete="off"
        aria-controls={listId}
        aria-expanded={results.length > 0}
        className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
      />
      {query.length >= 2 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-[1000] mt-1 max-h-80 w-full overflow-y-auto rounded-lg border border-neutral-200 bg-white text-sm shadow-lg dark:border-neutral-700 dark:bg-neutral-900"
        >
          {loading && results.length === 0 && <li className="px-3 py-2 text-neutral-500">Searching…</li>}
          {!loading && results.length === 0 && <li className="px-3 py-2 text-neutral-500">No matches</li>}
          {results.map((r) => (
            <li key={`${r.type}-${r.id}`} role="option" aria-selected={false}>
              <Link
                href={r.type === "station" ? `/station/${r.id}` : `/region/${r.region}`}
                className="block px-3 py-2 hover:bg-neutral-100 dark:hover:bg-neutral-800"
              >
                <span className="font-medium">{r.name}</span>
                <span className="ml-2 text-xs text-neutral-500">
                  {r.type === "area" ? r.context : r.context ?? ""} · {REGION_NAMES[r.region]}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
