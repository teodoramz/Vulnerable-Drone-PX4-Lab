import { useEffect, useState } from "react";

import api from "../../api/client";
import type { SiteDef } from "../../components/map/site";

/** Loads the site definition once; it is static for the deployment. */
export function useSite() {
  const [site, setSite] = useState<SiteDef | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<SiteDef>("/api/site")
      .then((r) => !cancelled && setSite(r.data))
      .catch((e) => !cancelled && setError(e?.message ?? "could not load the site definition"));
    return () => {
      cancelled = true;
    };
  }, []);

  return { site, error };
}
