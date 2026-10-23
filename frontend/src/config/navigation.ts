import {
  BellRing,
  Boxes,
  Bug,
  Building2,
  Cloud,
  FileLock2,
  FileText,
  Globe,
  History,
  LayoutDashboard,
  Network,
  Radar,
  Server,
  Settings,
  ShieldAlert,
  Users,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  label: string;
  path: string;
  icon: LucideIcon;
  permission: string;
};

export type NavSection = {
  title: string;
  items: NavItem[];
};

export const navigationSections: NavSection[] = [
  {
    title: "Overview",
    items: [
      {
        label: "Dashboard",
        path: "/dashboard",
        icon: LayoutDashboard,
        permission: "risk:read",
      },
    ],
  },
  {
    title: "Assets",
    items: [
      {
        label: "Companies",
        path: "/companies",
        icon: Building2,
        permission: "company:read",
      },
      {
        label: "Asset Inventory",
        path: "/assets",
        icon: Boxes,
        permission: "asset:read",
      },
      { label: "Domains", path: "/domains", icon: Globe, permission: "asset:read" },
      {
        label: "IP Addresses & Services",
        path: "/ips",
        icon: Server,
        permission: "asset:read",
      },
      { label: "APIs", path: "/apis", icon: Network, permission: "asset:read" },
      { label: "Cloud Assets", path: "/cloud", icon: Cloud, permission: "asset:read" },
      {
        label: "Certificates",
        path: "/certificates",
        icon: FileLock2,
        permission: "certificate:read",
      },
    ],
  },
  {
    title: "Risk",
    items: [
      {
        label: "Vulnerabilities",
        path: "/vulnerabilities",
        icon: Bug,
        permission: "vulnerability:read",
      },
      {
        label: "Findings",
        path: "/findings",
        icon: ShieldAlert,
        permission: "finding:read",
      },
      {
        label: "Change History",
        path: "/changes",
        icon: History,
        permission: "change:read",
      },
    ],
  },
  {
    title: "Operations",
    items: [
      { label: "Alerts", path: "/alerts", icon: BellRing, permission: "alert:read" },
      {
        label: "Reports",
        path: "/reports",
        icon: FileText,
        permission: "report:read",
      },
      { label: "Scans", path: "/scans", icon: Radar, permission: "scan:read" },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Users & Roles", path: "/users", icon: Users, permission: "user:read" },
      {
        label: "Settings",
        path: "/settings",
        icon: Settings,
        permission: "company:read",
      },
    ],
  },
];

export const navItems: NavItem[] = navigationSections.flatMap(
  (section) => section.items,
);

export function findNavItem(pathname: string): NavItem | undefined {
  return navItems.find(
    (item) => pathname === item.path || pathname.startsWith(`${item.path}/`),
  );
}
