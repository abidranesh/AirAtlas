import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import RegionView from "@/components/RegionView";
import { Skeleton } from "@/components/ui";
import { REGION_NAMES } from "@/lib/format";
import { REGION_CODES, type RegionCode } from "@/lib/types";

const isRegion = (c: string): c is RegionCode => (REGION_CODES as readonly string[]).includes(c);

export function generateStaticParams() {
  return REGION_CODES.map((code) => ({ code }));
}

export async function generateMetadata({ params }: PageProps<"/region/[code]">): Promise<Metadata> {
  const { code } = await params;
  return isRegion(code)
    ? { title: `${REGION_NAMES[code]} air quality`, description: `Live and historical air quality across ${REGION_NAMES[code]}.` }
    : {};
}

async function Region({ params }: { params: PageProps<"/region/[code]">["params"] }) {
  const { code } = await params;
  if (!isRegion(code)) notFound();
  return <RegionView code={code} />;
}

export default function Page({ params }: PageProps<"/region/[code]">) {
  return (
    <Suspense fallback={<Skeleton className="h-[70vh]" />}>
      <Region params={params} />
    </Suspense>
  );
}
