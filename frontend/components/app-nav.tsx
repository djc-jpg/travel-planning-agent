"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "规划" },
  { href: "/chat", label: "对话调优" },
  { href: "/history", label: "历史记录" },
  { href: "/diagnostics", label: "系统状态" }
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <header className="border-b bg-card">
      <div className="page-container flex items-center justify-between py-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-primary">trip-agent</p>
          <p className="text-xs text-muted-foreground">智能行程规划台</p>
        </div>
        <nav className="flex flex-wrap gap-2">
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                data-testid={`nav-${item.href === "/" ? "plan" : item.href.slice(1)}`}
                className={cn(
                  "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "bg-secondary text-secondary-foreground hover:bg-accent"
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
