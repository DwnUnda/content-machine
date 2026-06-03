import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";

import "./globals.css";


export const metadata: Metadata = {
  title: "Home Dry Lab Content Machine",
  description: "Local-first editorial workflow app for Home Dry Lab.",
};


export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

