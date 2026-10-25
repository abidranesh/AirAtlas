import type { Metadata } from "next";
import Link from "next/link";
import { Card } from "@/components/ui";
import { INSIGHTS } from "@/lib/insights";

export const metadata: Metadata = {
  title: "Insights",
  description: "Festival nights, Kerala's monsoon, UAE dust, Germany's heating season and Tamil Nadu's industrial monitors, computed from stored data.",
};

export default function Page() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-bold sm:text-3xl">Insights</h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Each page is computed from the measurements AirAtlas has stored, with its method and sample size shown. Where the data is thin, the page says
          so.
        </p>
      </header>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {INSIGHTS.map((i) => (
          <li key={i.slug}>
            <Link href={`/insights/${i.slug}`} className="group block h-full">
              <Card className="h-full transition-colors group-hover:border-sky-600">
                <p className="text-xs tracking-wide text-neutral-500 uppercase">{i.region}</p>
                <h2 className="mt-1 font-semibold group-hover:underline">{i.title}</h2>
                <p className="mt-1 text-sm text-neutral-700 dark:text-neutral-300">{i.blurb}</p>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
