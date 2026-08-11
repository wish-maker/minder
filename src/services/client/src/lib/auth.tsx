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
    };
  } catch {
    return { username: "", email: "", role: "" };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(
    () => sessionStorage.getItem(TOKEN_KEY) || "",
  );
  const claims = useMemo(() => decodeJwtClaims(token), [token]);

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
        isAuthenticated: !!token,
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
