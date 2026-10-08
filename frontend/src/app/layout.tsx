import type { Metadata } from "next";
import localFont from "next/font/local";
import { SiteHeader } from "@/components/SiteHeader";
import { RoleGate } from "@/components/RoleGate";
import "./globals.css";

// Atkinson Hyperlegible: designed for low-vision readers. Many tenants read
// English as a second language, so legibility is not a nicety here.
const atkinson = localFont({
  src: [
    { path: "./fonts/atkinson-hyperlegible-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/atkinson-hyperlegible-latin-700-normal.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-atkinson",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "FairTriage NT", template: "%s | FairTriage NT" },
  description: "Housing repair reports for Northern Territory communities, ranked by need and explained.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-AU" className={atkinson.variable}>
      <body className="flex min-h-screen flex-col font-sans">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-paper focus:px-4 focus:py-2">
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" className="mx-auto w-full min-w-0 max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
          <RoleGate>{children}</RoleGate>
        </main>
        <footer className="border-t border-line bg-paper">
          <div className="mx-auto max-w-7xl px-4 py-5 text-sm text-muted sm:px-6">
            FairTriage NT recommends; a person approves every decision. Where you live never changes your place in the queue.
          </div>
        </footer>
      </body>
    </html>
  );
}
