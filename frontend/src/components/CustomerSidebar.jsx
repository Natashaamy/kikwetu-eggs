import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

function CustomerSidebar({ onNavigate }) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const links = [["/customer/dashboard", "Dashboard"], ["/customer/order", "Order Now"], ["/customer/orders", "My Orders"], ["/customer/profile", "Profile"]];
  async function handleLogout() {
    await logout();
    onNavigate();
    navigate("/login");
  }
  return <nav className="sidebar-navigation" aria-label="Customer navigation">
    <p className="sidebar-label">Customer</p>
    {links.map(([to, label]) => <NavLink key={to} to={to} onClick={onNavigate}>{label}</NavLink>)}
    <button type="button" className="sidebar-logout" onClick={handleLogout}>Logout</button>
  </nav>;
}

export default CustomerSidebar;
