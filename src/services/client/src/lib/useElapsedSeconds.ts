import { useEffect, useRef, useState } from "react";

/** Ticks up every second while `active` -- for operations with no real
 * progress signal from the backend (a single blocking request), so this is
 * deliberately just an elapsed-time counter, not a real progress bar. Still
 * meaningfully better than a static "please wait" sentence for a
 * multi-second/minute operation: it proves the page hasn't frozen, and
 * "2m14s elapsed" reads as "still working" in a way a motionless message
 * doesn't. Shared by ModelManagementPage's pull-model wait and VoicePage's
 * recording timer. */
export function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  const startRef = useRef<number>(0);

  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return;
    }
    startRef.current = Date.now();
    const interval = setInterval(() => {
      setSeconds(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [active]);

  return seconds;
}

export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m${s.toString().padStart(2, "0")}s` : `${s}s`;
}
