import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { runModel } from "../api";
import type { Overrides } from "../api";

/**
 * Debounced live recalc. Keeps the latest `overrides` and only re-runs the
 * model ~300ms after the user stops editing inputs.
 */
export function useRun(
  modelId: string | null,
  overrides: Overrides,
  enabled: boolean,
) {
  const [debounced, setDebounced] = useState(overrides);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(overrides), 300);
    return () => clearTimeout(id);
  }, [overrides]);

  const query = useQuery({
    queryKey: ["run", modelId, debounced],
    queryFn: () => runModel(modelId as string, debounced),
    enabled: enabled && !!modelId,
    placeholderData: (prev) => prev,
  });

  return { data: query.data, isFetching: query.isFetching, error: query.error };
}
