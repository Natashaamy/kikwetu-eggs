import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function ProtectedRoute({ role }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.loading) return <div className="auth-loading">Checking your session…</div>;
  if (!auth.authenticated) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (auth.role !== role) return <Navigate to={auth.role === "admin" ? "/admin/dashboard" : "/customer/dashboard"} replace />;
  return <Outlet />;
}
