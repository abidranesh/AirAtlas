import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import InsightView from "@/components/InsightView";
import { Skeleton } from "@/components/ui";
import { INSIGHTS, isInsight } from "@/lib/insights";

export function generateStaticParams() {
  return INSIGHTS.map(({ slug }) => ({ slug }));
}

export async function generateMetadata({ params }: PageProps<"/insights/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const info = INSIGHTS.find((i) => i.slug === slug);
  return info ? { title: info.title, description: info.blurb } : {};
}

async function Insight({ params }: { params: PageProps<"/insights/[slug]">["params"] }) {
  const { slug } = await params;
  if (!isInsight(slug)) notFound();
  return <InsightView slug={slug} />;
}

export default function Page({ params }: PageProps<"/insights/[slug]">) {
  return (
    <Suspense fallback={<Skeleton className="h-[70vh]" />}>
      <Insight params={params} />
    </Suspense>
  );
}
