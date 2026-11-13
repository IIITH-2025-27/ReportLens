import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  useEffect(() => {
    if (!getToken()) return;
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const out = () => setUser(null);
    window.addEventListener("reportlens:signed-out", out);
    return () => window.removeEventListener("reportlens:signed-out", out);
  }, []);

  const accept = useCallback(({ token, user }) => {
    setToken(token);
    setUser(user);
    return user;
  }, []);
  const signin = useCallback((data) => api.signin(data).then(accept), [accept]);
  const signup = useCallback((data) => api.signup(data).then(accept), [accept]);
  const signout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, loading, signin, signup, signout }}>{children}</AuthContext.Provider>;
}
