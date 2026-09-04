export default function PlaceholderPage({ title, description }) {
  return <><section className="page-heading"><div><p className="eyebrow">Admin</p><h1>{title}</h1><p className="page-description">{description}</p></div></section><section className="panel"><div className="state-message empty-state"><strong>Coming soon.</strong><span>This area is ready for a future development stage.</span></div></section></>;
}
