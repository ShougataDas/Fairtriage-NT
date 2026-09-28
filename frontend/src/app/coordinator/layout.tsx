import type { Metadata } from "next";
import { ReaderBar } from "@/components/ReaderBar";

export const metadata: Metadata = { title: "Staff" };

export default function CoordinatorLayout({ children }: LayoutProps<"/coordinator">) {
  return (
    <>
      <ReaderBar />
      {children}
    </>
  );
}
