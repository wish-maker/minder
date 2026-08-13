/** Pure JWT-claim helpers, split out of auth.tsx so they're unit-testable
 * without rendering the AuthProvider — and so auth.tsx stays a
 * components-only module (React Fast Refresh only works cleanly when a file
 * exports components alone). #502 */

export interface JwtClaims {
  username: string;
  email: string;
  role: string;
  exp: number; // seconds since epoch; 0 when the token carries no expiry
}

/** True once the token's `exp` has passed. Tokens without an `exp` (exp === 0)
 * are treated as non-expiring so this never regresses such tokens to logged-out. */
export function isExpired(exp: number): boolean {
  return exp > 0 && Date.now() >= exp * 1000;
}

/** Decode the display claims (username/email/role/exp) straight from a JWT's
 * payload segment. Malformed/absent input fails open into empty strings + exp 0
 * rather than throwing: a broken token should read as "not really logged in",
 * not crash the app. Every claim lives in the token already, so decoding it
 * fresh keeps exactly one source of truth for "who is this" regardless of which
 * path (local login, SSO callback, reload from sessionStorage) produced it. */
export function decodeJwtClaims(jwt: string): JwtClaims {
  try {
    const payload = jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(atob(payload)) as Record<string, unknown>;
    return {
      username: typeof decoded.username === "string" ? decoded.username : "",
      email: typeof decoded.email === "string" ? decoded.email : "",
      role: typeof decoded.role === "string" ? decoded.role : "",
      exp: typeof decoded.exp === "number" ? decoded.exp : 0,
    };
  } catch {
    return { username: "", email: "", role: "", exp: 0 };
  }
}
