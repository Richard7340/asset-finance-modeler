import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { runModel } from "../api";

/**
 * Debounced live recalc. Keeps the latest `overrides` and only re-runs the
 * model ~300ms after the user stops moving sliders.
 */
export function useRun(overrides: Record<string, number>, enabled: boolean) {
  const [debounced, setDebounced] = useState(overrides);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(overrides), 300);
    return () => clearTimeout(id);
  }, [overrides]);

  const query = useQuery({
    queryKey: ["run", debounced],
    queryFn: () => runModel(debounced),
    enabled,
    placeholderData: (prev) => prev,
  });

  return { data: query.data, isFetching: query.isFetching, error: query.error };
}
