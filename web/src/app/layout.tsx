import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = { title: "triagekit", description: "Human-in-the-loop text triage" };
export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="snorkel-blue">
      <body><Nav /><main>{children}</main></body>
    </html>
  );
}
