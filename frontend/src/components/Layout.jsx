import { NavLink } from "react-router-dom";

function Layout({ children }) {
  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="header-content">
          <div className="brand-group">
            <div>
              <p className="eyebrow">Kikwetu Eggs</p>
              <p className="brand-subtitle">Simple stock and sales management</p>
            </div>
          </div>

          <nav className="main-navigation" aria-label="Main navigation">
            <NavLink
              to="/order"
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              Order Now
            </NavLink>
            <NavLink
              to="/dashboard"
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/products"
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              Products
            </NavLink>
            <NavLink
              to="/orders"
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              Orders
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="page-container">{children}</main>
    </div>
  );
}

export default Layout;
