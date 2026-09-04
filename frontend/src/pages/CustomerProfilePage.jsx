import { useEffect, useState } from "react";
import { getCustomerProfile, updateCustomerProfile } from "../api/customerPortal.js";
import { useAuth } from "../context/AuthContext.jsx";

export default function CustomerProfilePage() {
  const { refreshAuth } = useAuth();
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState({ name: "", phone_number: "" });
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getCustomerProfile().then((data) => {
      setProfile(data.profile);
      setForm({ name: data.profile.name, phone_number: data.profile.phone_number });
    }).catch(() => setError("Your profile could not be loaded."));
  }, []);

  async function saveProfile(event) {
    event.preventDefault(); setError(""); setMessage("");
    if (!form.name.trim() || !form.phone_number.trim()) return setError("Name and phone number are required.");
    setSaving(true);
    try {
      const result = await updateCustomerProfile({ name: form.name.trim(), phone_number: form.phone_number.trim() });
      setProfile(result.profile); setForm(result.profile); setMessage(result.message); await refreshAuth();
    } catch (requestError) { setError(requestError.message || "Profile could not be updated."); }
    finally { setSaving(false); }
  }

  const initial = profile?.name?.trim().charAt(0).toUpperCase() || "?";
  return <>
    <section className="page-heading"><div><p className="eyebrow">Customer account</p><h1>My Profile</h1><p className="page-description">Manage your personal account information.</p></div></section>
    {!profile ? <section className="panel"><p className={`state-message ${error ? "error-state" : ""}`}>{error || "Loading your profile…"}</p></section> : <div className="profile-page-grid">
      <aside className="profile-summary-card"><div className="profile-avatar" aria-hidden="true">{initial}</div><h2>{profile.name}</h2><p>Customer Account</p><dl><div><dt>Phone</dt><dd>{profile.phone_number}</dd></div></dl></aside>
      <section className="panel personal-info-card"><div className="panel-heading"><p className="section-number">01</p><div><h2>Personal Information</h2><p>Keep your contact details up to date.</p></div></div><form className="profile-form" onSubmit={saveProfile}><label>Name<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} autoComplete="name" required /></label><label>Phone Number<input value={form.phone_number} onChange={(event) => setForm({ ...form, phone_number: event.target.value })} autoComplete="tel" required /></label>{error && <p className="message error-message">{error}</p>}{message && <p className="message success-message" role="status">{message}</p>}<div className="profile-save-row"><button type="submit" disabled={saving}>{saving ? "Saving…" : "Save Changes"}</button></div></form></section>
    </div>}
  </>;
}
