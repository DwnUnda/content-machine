"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";


const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/articles", label: "Articles" },
  { href: "/products", label: "Products" },
  { href: "/clusters", label: "Clusters" },
  { href: "/sources", label: "Sources" },
  { href: "/settings", label: "Settings" },
  { href: "/logs", label: "Logs" },
];


export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-kicker">Local-first editorial ops</div>
          <div className="brand-title">Home Dry Lab Content Machine</div>
          <p className="brand-copy">
            Research-backed Australian content drafting, with draft-only WordPress export safeguards.
          </p>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} data-active={pathname.startsWith(item.href)}>
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}

