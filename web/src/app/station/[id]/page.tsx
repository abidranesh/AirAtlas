import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import StationView from "@/components/StationView";
import { Skeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Station", description: "Current air quality, health advice and trends for one station." };

async function Station({ params }: { params: PageProps<"/station/[id]">["params"] }) {
  const { id } = await params;
  const n = Number(id);
  if (!Number.isInteger(n) || n <= 0) notFound();
  return <StationView id={n} />;
}

export default function Page({ params }: PageProps<"/station/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="h-[70vh]" />}>
      <Station params={params} />
    </Suspense>
  );
}
