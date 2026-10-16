import { useCallback, useEffect, useRef, useState } from "react";

export interface Resource<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => void;
  setData: (update: (prev: T | undefined) => T | undefined) => void;
}

/** Load async data, re-running when `deps` change. Stale responses are ignored. */
export function useResource<T>(load: () => Promise<T>, deps: unknown[]): Resource<T> {
  const [data, setDataState] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let current = true;
    setLoading(true);
    loadRef
      .current()
      .then((d) => {
        if (current) {
          setDataState(d);
          setError(undefined);
        }
      })
      .catch((e: unknown) => {
        if (current) setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback(
    (update: (prev: T | undefined) => T | undefined) => setDataState(update),
    [],
  );
  return { data, error, loading, reload, setData };
}
