import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

function AdminSidebar({ onNavigate }) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const links = [["/admin/dashboard", "Dashboard"], ["/admin/products", "Products"], ["/admin/orders", "Orders"], ["/admin/customers", "Customers"], ["/admin/reports", "Reports"]];

  async function handleLogout() {
    onNavigate();
    await logout();
    navigate("/login");
  }

  return <nav className="sidebar-navigation" aria-label="Admin navigation">
    <p className="sidebar-label">Admin</p>
    {links.map(([to, label]) => <NavLink key={to} to={to} onClick={onNavigate}>{label}</NavLink>)}
    <button type="button" className="sidebar-logout" onClick={handleLogout}><span aria-hidden="true">↪</span> Logout</button>
  </nav>;
}

export default AdminSidebar;
