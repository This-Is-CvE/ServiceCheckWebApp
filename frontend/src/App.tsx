import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { api, getToken, setToken } from "./api";
import { User } from "./types";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Customers from "./pages/Customers";
import Checks from "./pages/Checks";
import CheckDetail from "./pages/CheckDetail";
import Onboardings from "./pages/Onboardings";
import OnboardingDetail from "./pages/OnboardingDetail";
import Catalog from "./pages/Catalog";
import Users from "./pages/Users";

const AuthCtx = createContext<User | null>(null);
export const useUser = () => useContext(AuthCtx)!;

function Shell() {
  const [user, setUser] = useState<User | null>(null);
  const nav = useNavigate();
  useEffect(() => {
    if (!getToken()) { nav("/login"); return; }
    api<User>("/auth/me").then(setUser).catch(() => nav("/login"));
  }, [nav]);
  if (!user) return <div className="center muted">Lade …</div>;
  const logout = () => { setToken(null); nav("/login"); };
  return (
    <AuthCtx.Provider value={user}>
      <div className="layout">
        <aside className="side">
          <div className="brand">Service Check<small>&amp; Onboarding</small></div>
          <nav>
            <NavLink to="/" end>Übersicht</NavLink>
            <div className="nav-group">Modul 1</div>
            <NavLink to="/checks">Service Checks</NavLink>
            <div className="nav-group">Modul 2</div>
            <NavLink to="/onboardings">Onboardings</NavLink>
            <div className="nav-group">Stammdaten</div>
            <NavLink to="/customers">Kunden</NavLink>
            <NavLink to="/catalog">Kataloge &amp; Vorlagen</NavLink>
            {user.role === "admin" && <NavLink to="/users">Benutzer</NavLink>}
          </nav>
          <div className="side-foot">
            <div>{user.full_name || user.username}<small>{user.role === "admin" ? "Administrator" : "Consultant"}</small></div>
            <button className="btn ghost" onClick={logout}>Abmelden</button>
          </div>
        </aside>
        <main className="main"><Outlet /></main>
      </div>
    </AuthCtx.Provider>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        <Route path="customers" element={<Customers />} />
        <Route path="checks" element={<Checks />} />
        <Route path="checks/:id" element={<CheckDetail />} />
        <Route path="onboardings" element={<Onboardings />} />
        <Route path="onboardings/:id" element={<OnboardingDetail />} />
        <Route path="catalog" element={<Catalog />} />
        <Route path="users" element={<Users />} />
      </Route>
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  );
}
