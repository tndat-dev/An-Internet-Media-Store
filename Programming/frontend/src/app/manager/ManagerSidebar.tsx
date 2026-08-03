"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
  // Active when the current path is within this section.
  match: (pathname: string) => boolean;
};

const NAV_ITEMS: NavItem[] = [
  {
    href: "/manager/products",
    label: "Products",
    match: (path) => path.startsWith("/manager/products") && !path.startsWith("/manager/products/history"),
  },
  {
    href: "/manager/products/history",
    label: "Product history",
    match: (path) => path.startsWith("/manager/products/history"),
  },
  {
    href: "/manager/analytics",
    label: "Analytics",
    match: (path) => path.startsWith("/manager/analytics"),
  },
  {
    href: "/manager/orders",
    label: "Pending orders",
    match: (path) => path.startsWith("/manager/orders"),
  },
  {
    href: "/manager/refunds",
    label: "Refunding orders",
    match: (path) => path.startsWith("/manager/refunds"),
  },
];

export function ManagerSidebar() {
  const pathname = usePathname() ?? "";

  return (
    <aside className="manager-sidebar" aria-label="Manager navigation">
      <p className="manager-sidebar-title">Product Manager</p>
      <nav className="manager-sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const active = item.match(pathname);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={active ? "manager-sidebar-link is-active" : "manager-sidebar-link"}
              aria-current={active ? "page" : undefined}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
