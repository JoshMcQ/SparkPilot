"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { fetchAuthMe, type AuthMe } from "@/lib/api";

export function isInternalAdmin(auth: AuthMe | null): boolean {
  return auth?.is_internal_admin === true;
}

type UseInternalAdminOptions = {
  redirectIfDenied?: boolean;
};

type InternalAdminState = {
  loading: boolean;
  auth: AuthMe | null;
  isInternalAdmin: boolean;
  error: string | null;
};

export function useInternalAdmin(options: UseInternalAdminOptions = {}): InternalAdminState {
  const router = useRouter();
  const [state, setState] = useState<InternalAdminState>({
    loading: true,
    auth: null,
    isInternalAdmin: false,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const auth = await fetchAuthMe();
        if (cancelled) {
          return;
        }
        const internal = isInternalAdmin(auth);
        setState({
          loading: false,
          auth,
          isInternalAdmin: internal,
          error: null,
        });
        if (options.redirectIfDenied && !internal) {
          router.replace("/access?notice=internal-tools-denied");
        }
      } catch (error: unknown) {
        if (cancelled) {
          return;
        }
        setState({
          loading: false,
          auth: null,
          isInternalAdmin: false,
          error: error instanceof Error ? error.message : "Failed to resolve auth state.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [options.redirectIfDenied, router]);

  return state;
}
