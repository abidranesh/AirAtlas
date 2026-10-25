import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import Link from "next/link";
import { REGION_NAMES } from "@/lib/format";
import { REGION_CODES } from "@/lib/types";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "AirAtlas: air quality in Tamil Nadu, Kerala, the UAE and Germany", template: "%s · AirAtlas" },
  description:
    "Live and historical air quality on each country's own AQI standard and on a common scale, with honest labels for modeled and missing data.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

const SHORT: Record<string, string> = { tamil_nadu: "Tamil Nadu", kerala: "Kerala", uae: "UAE", germany: "Germany" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[2000] focus:rounded focus:bg-white focus:px-3 focus:py-2">
          Skip to content
        </a>
        <header className="border-b border-neutral-200 dark:border-neutral-800">
          <nav aria-label="Main" className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
            <Link href="/" className="text-lg font-bold tracking-tight">
              Air<span className="text-sky-600">Atlas</span>
            </Link>
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {REGION_CODES.map((c) => (
                <li key={c}>
                  <Link href={`/region/${c}`} className="hover:underline" title={REGION_NAMES[c]}>
                    {SHORT[c]}
                  </Link>
                </li>
              ))}
              <li>
                <Link href="/compare" className="font-medium hover:underline">
                  Compare
                </Link>
              </li>
              <li>
                <Link href="/insights" className="font-medium hover:underline">
                  Insights
                </Link>
              </li>
            </ul>
          </nav>
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
          {children}
        </main>
        <footer className="border-t border-neutral-200 text-xs text-neutral-600 dark:border-neutral-800 dark:text-neutral-400">
          <div className="mx-auto max-w-6xl space-y-1 px-4 py-5">
            <p>
              Data: Central Pollution Control Board (data.gov.in, GODL-India) · Source: Umweltbundesamt (dl-de/by-2-0) · European
              Environment Agency (CC BY 4.0) · OpenAQ and its providers · Air quality and weather by Open-Meteo.com (CC BY 4.0,
              CAMS/ERA5) · NASA LANCE FIRMS · Boundaries: geoBoundaries (ODbL / dl-de/by-2-0) · Map © OpenStreetMap contributors.
            </p>
            <p>Modeled values are estimates, not measurements. AirAtlas is a portfolio project, not an official warning service.</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
