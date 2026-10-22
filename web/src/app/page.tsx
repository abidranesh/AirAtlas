import { Suspense } from "react";
import HomeView from "@/components/HomeView";
import { Skeleton } from "@/components/ui";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-[60vh]" />}>
      <HomeView />
    </Suspense>
  );
}
