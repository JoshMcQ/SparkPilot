import { fetchInternalTenants, type InternalTenantListItem } from "@/lib/api";

export type InternalTenantsListState =
  | { status: "ready"; rows: InternalTenantListItem[] }
  | { status: "error"; message: string };

export async function resolveInternalTenantsListState(
  fetchFn: () => Promise<InternalTenantListItem[]> = fetchInternalTenants,
): Promise<InternalTenantsListState> {
  try {
    const rows = await fetchFn();
    return { status: "ready", rows };
  } catch (error: unknown) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Failed to load internal tenants.",
    };
  }
}
