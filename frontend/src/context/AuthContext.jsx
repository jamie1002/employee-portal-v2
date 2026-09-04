import { createContext, useContext, useEffect, useState } from "react";
import * as authApi from "../api/auth.api";
import { clearStoredToken, getStoredToken, setStoredToken } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  // 只為了改密碼頁能預填「剛才登入用的密碼」（見 docs/UI-SPEC.md §3.3），
  // 純粹是記憶體內的暫存值，不寫入 localStorage，登出／改密碼成功後清除。
  const [recentLoginPassword, setRecentLoginPassword] = useState(null);

  useEffect(() => {
    if (!getStoredToken()) {
      setIsLoading(false);
      return;
    }

    authApi
      .getMe()
      .then(({ user: fetchedUser }) => setUser(fetchedUser))
      .catch(() => {
        clearStoredToken();
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  async function login(email, password) {
    const { token, user: loggedInUser } = await authApi.login(email, password);
    setStoredToken(token);
    setUser(loggedInUser);
    setRecentLoginPassword(password);
    return loggedInUser;
  }

  function logout() {
    clearStoredToken();
    setUser(null);
    setRecentLoginPassword(null);
  }

  async function changePassword(oldPassword, newPassword) {
    const { user: updatedUser } = await authApi.changePassword(oldPassword, newPassword);
    setUser(updatedUser);
    setRecentLoginPassword(null);
    return updatedUser;
  }

  return (
    <AuthContext.Provider
      value={{ user, isLoading, recentLoginPassword, login, logout, changePassword }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth() 必須在 AuthProvider 之內使用。");
  }
  return context;
}
