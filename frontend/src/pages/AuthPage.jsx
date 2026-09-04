import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { loginUser, registerCustomer } from "../api/auth.js";
import KikwetuLogo from "../components/KikwetuLogo.jsx";
import { useAuth } from "../context/AuthContext.jsx";

export default function AuthPage({ mode }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const registering = mode === "register";
  const [form, setForm] = useState({ name: "", phone_number: "", password: "", confirm_password: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!auth.loading && auth.authenticated) {
    return <Navigate to={auth.role === "admin" ? "/admin/dashboard" : "/customer/dashboard"} replace />;
  }

  function handleChange(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (registering && form.password !== form.confirm_password) {
      setError("Passwords do not match.");
      return;
    }
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setSubmitting(true);
    try {
      const result = registering
        ? await registerCustomer({ name: form.name, phone_number: form.phone_number, password: form.password })
        : await loginUser({ username: form.name, password: form.password });
      auth.setAuthenticated(result);
      navigate(result.role === "admin" ? "/admin/dashboard" : "/customer/dashboard", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  return <main className="auth-shell"><section className="auth-card">
    <div className="auth-brand">
      <KikwetuLogo size="large" />
      <h1>{registering ? "Create Account" : "Login"}</h1>
    </div>
    <p className="page-description">
      {registering
        ? "Create your Kikwetu Eggs customer account."
        : "Enter your name and password to continue."}
    </p>
    <form className="auth-form" onSubmit={handleSubmit}>
      <label>Name<input name="name" value={form.name} onChange={handleChange} required autoComplete="username" /></label>
      {registering && <label>Phone Number<input name="phone_number" value={form.phone_number} onChange={handleChange} required autoComplete="tel" /></label>}
      <label>Password<input type="password" name="password" value={form.password} onChange={handleChange} required minLength="8" autoComplete={registering ? "new-password" : "current-password"} /></label>
      {registering && <label>Confirm Password<input type="password" name="confirm_password" value={form.confirm_password} onChange={handleChange} required minLength="8" autoComplete="new-password" /></label>}
      {error && <p className="message error-message">{error}</p>}
      <button disabled={submitting}>{submitting ? "Please wait…" : registering ? "Register" : "Login"}</button>
    </form>
    <div className="auth-links">
      {registering ? <span>Already have an account? <Link to="/login">Login</Link></span> : <span>Don&apos;t have an account? <Link to="/register">Register</Link></span>}
    </div>
  </section></main>;
}
