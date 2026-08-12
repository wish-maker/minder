import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import { apiBaseUrl } from "./api";

// Same sessionStorage key the old plugin_config.html/model_management.html
// pages used, kept for continuity across the migration (#422 -> this client).
const TOKEN_KEY = "minder_jwt";

interface JwtClaims {
  username: string;
  email: string;
  role: string;
  exp: number; // seconds since epoch; 0 when the token carries no expiry
}

/** True once the token's `exp` has passed. Tokens without an `exp` (exp === 0)
 * are treated as non-expiring so this never regresses such tokens to logged-out. */
function isExpired(exp: number): boolean {
  return exp > 0 && Date.now() >= exp * 1000;
}

interface AuthContextValue {
  token: string;
  username: string;
  email: string;
  role: string;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginWithToken: (jwt: string) => void;
  register: (
    username: string,
    email: string,
    password: string,
  ) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function parseError(res: Response): Promise<string> {
  const data = await res.json().catch(() => ({}) as { detail?: string });
  return data.detail || `Request failed (${res.status})`;
}

/** Every display claim (username/email/role) lives in the JWT payload
 * already -- decoded fresh from the token itself rather than duplicated
 * into separate state, so there is exactly one source of truth for "who is
 * this" no matter which path (local login, SSO callback, page reload from
 * sessionStorage) produced the token. Malformed/absent input fails open
 * into empty strings rather than throwing: a broken token should read as
 * "not really logged in", not crash the app. */
function decodeJwtClaims(jwt: string): JwtClaims {
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(
    () => sessionStorage.getItem(TOKEN_KEY) || "",
  );
  const claims = useMemo(() => decodeJwtClaims(token), [token]);
  // An expired JWT left in sessionStorage must NOT read as logged-in — otherwise
  // the header shows a username while every write silently 401s. Treated as
  // not-authenticated so the app routes back to login (#472-adjacent UX gap).
  const authenticated = !!token && !isExpired(claims.exp);

  const login = useCallback(async (user: string, password: string) => {
    const res = await fetch(`${apiBaseUrl}/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: user, password }),
    });
    if (!res.ok) throw new Error(await parseError(res));
    const data = (await res.json()) as { access_token: string };
    setToken(data.access_token);
    sessionStorage.setItem(TOKEN_KEY, data.access_token);
  }, []);

  const register = useCallback(
    async (user: string, email: string, password: string) => {
      const res = await fetch(`${apiBaseUrl}/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: user, email, password }),
      });
      if (!res.ok) throw new Error(await parseError(res));
    },
    [],
  );

  const loginWithToken = useCallback((jwt: string) => {
    setToken(jwt);
    sessionStorage.setItem(TOKEN_KEY, jwt);
  }, []);

  const logout = useCallback(() => {
    setToken("");
    sessionStorage.removeItem(TOKEN_KEY);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        token,
        username: claims.username,
        email: claims.email,
        role: claims.role,
        isAuthenticated: authenticated,
        login,
        loginWithToken,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
