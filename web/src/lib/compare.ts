import type { MonthlyRow } from "./types";

/** One row per month with a column per region, ready for Recharts. */
export function pivotMonthly(rows: MonthlyRow[]): Record<string, number | string>[] {
  const byMonth = new Map<string, Record<string, number | string>>();
  for (const r of rows) {
    const row = byMonth.get(r.month) ?? { month: r.month };
    row[r.region] = r.pm25;
    byMonth.set(r.month, row);
  }
  return [...byMonth.values()].sort((a, b) => String(a.month).localeCompare(String(b.month)));
}
