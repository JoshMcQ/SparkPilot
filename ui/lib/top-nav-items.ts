export type NavItem = {
  href: string;
  label: string;
};

const BASE_NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/onboarding/aws", label: "Start Here" },
  { href: "/environments", label: "Environments" },
  { href: "/runs", label: "Runs" },
  { href: "/integrations", label: "Integrations" },
  { href: "/costs", label: "Costs" },
  { href: "/policies", label: "Policies" },
  { href: "/access", label: "Access" },
  { href: "/settings", label: "Settings" },
];

const INTERNAL_ADMIN_NAV_ITEMS: NavItem[] = [
  { href: "/internal/tenants", label: "Tenants" },
];

export function buildTopNavItems(isInternalAdmin: boolean): NavItem[] {
  return isInternalAdmin ? INTERNAL_ADMIN_NAV_ITEMS : BASE_NAV_ITEMS;
}
