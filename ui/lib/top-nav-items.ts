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

export function buildTopNavItems(isInternalAdmin: boolean): NavItem[] {
  if (!isInternalAdmin) {
    return BASE_NAV_ITEMS;
  }
  return [...BASE_NAV_ITEMS, { href: "/internal/tenants", label: "Internal" }];
}
