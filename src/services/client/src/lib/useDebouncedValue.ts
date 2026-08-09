import { useEffect, useState } from "react";

/** Returns `value`, but only updates after it's been stable for `delayMs` --
 * for search-as-you-type inputs that would otherwise fire one network
 * request per keystroke. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
