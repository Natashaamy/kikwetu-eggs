import { useEffect, useState } from "react";
import { getCustomerProfile } from "../api/customerPortal.js";

export default function CustomerProfilePage() {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { getCustomerProfile().then((data) => setProfile(data.profile)).catch(() => setError("Your profile could not be loaded.")); }, []);
  return <><section className="page-heading"><div><p className="eyebrow">Customer Portal</p><h1>Profile</h1><p className="page-description">The customer details connected to your orders.</p></div></section><section className="panel profile-panel">{error ? <p className="message error-message">{error}</p> : !profile ? <p className="state-message">Loading your profile…</p> : <dl className="details-grid"><div><dt>Name</dt><dd>{profile.name}</dd></div><div><dt>Phone Number</dt><dd>{profile.phone_number}</dd></div></dl>}</section></>;
}
