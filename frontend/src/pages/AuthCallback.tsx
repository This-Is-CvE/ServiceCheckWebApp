import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { setToken } from "../api";

/** Nimmt das Token aus dem URL-Fragment (nach der Entra-Anmeldung) entgegen. */
export default function AuthCallback() {
  const nav = useNavigate();
  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (token) {
      setToken(token);
      window.history.replaceState(null, "", "/auth/callback");
      nav("/", { replace: true });
    } else {
      nav("/login?error=invalid_token", { replace: true });
    }
  }, [nav]);
  return <div className="center muted">Anmeldung wird abgeschlossen …</div>;
}
