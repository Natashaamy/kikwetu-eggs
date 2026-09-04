import { Navigate, Route, Routes } from "react-router-dom";

import AdminLayout from "./components/AdminLayout.jsx";
import CustomerLayout from "./components/CustomerLayout.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import AuthPage from "./pages/AuthPage.jsx";
import CreateOrderPage from "./pages/CreateOrderPage.jsx";
import CustomerDashboardPage from "./pages/CustomerDashboardPage.jsx";
import CustomerProfilePage from "./pages/CustomerProfilePage.jsx";
import CustomersPage from "./pages/CustomersPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import MyOrdersPage from "./pages/MyOrdersPage.jsx";
import OrdersPage from "./pages/OrdersPage.jsx";
import ProductsPage from "./pages/ProductsPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route element={<ProtectedRoute role="admin" />}>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="products" element={<ProductsPage />} />
          <Route path="orders" element={<OrdersPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="reports" element={<ReportsPage />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute role="customer" />}>
        <Route path="/customer" element={<CustomerLayout />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<CustomerDashboardPage />} />
          <Route path="order-now" element={<CreateOrderPage />} />
          <Route path="order" element={<Navigate to="../order-now" replace />} />
          <Route path="orders" element={<MyOrdersPage />} />
          <Route path="profile" element={<CustomerProfilePage />} />
        </Route>
      </Route>
      <Route path="/dashboard" element={<Navigate to="/admin/dashboard" replace />} />
      <Route path="/products" element={<Navigate to="/admin/products" replace />} />
      <Route path="/orders" element={<Navigate to="/admin/orders" replace />} />
      <Route path="/order" element={<Navigate to="/customer/order-now" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default App;
