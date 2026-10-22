import type { Metadata } from "next";
import { Suspense } from "react";
import CompareView from "@/components/CompareView";
import { Skeleton } from "@/components/ui";

export const metadata: Metadata = {
  title: "Compare regions",
  description: "Chennai, Kochi, Dubai and Berlin on the European AQI or against WHO PM2.5 guidelines.",
};

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-[60vh]" />}>
      <CompareView />
    </Suspense>
  );
}
