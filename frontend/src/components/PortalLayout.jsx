import { useState } from "react";
import { Outlet } from "react-router-dom";

import KikwetuLogo from "./KikwetuLogo.jsx";

function PortalLayout({ Sidebar, areaLabel }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return <div className="portal-shell">
    <header className="mobile-header"><strong>Kikwetu Eggs</strong><span>{areaLabel}</span><button type="button" onClick={() => setMenuOpen((open) => !open)}>{menuOpen ? "Close" : "Menu"}</button></header>
    <aside className={`portal-sidebar${menuOpen ? " open" : ""}`}>
      <div className="sidebar-brand">
        <KikwetuLogo size="small" />
        <span>{areaLabel}</span>
      </div>
      <Sidebar onNavigate={() => setMenuOpen(false)} />
    </aside>
    {menuOpen && <button className="sidebar-backdrop" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}
    <main className="portal-content"><Outlet /></main>
  </div>;
}

export default PortalLayout;
