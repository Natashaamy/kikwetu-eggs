import { useEffect, useMemo, useState } from "react";
import { addProductStock, createProduct, deleteProduct, getProducts, setProductStock, updateProduct } from "../api/products.js";

const EMPTY_FORM = { name: "", description: "", unit_name: "", unit_price: "", is_active: true };
const money = new Intl.NumberFormat("en-KE", { style: "currency", currency: "KES", minimumFractionDigits: 0 });
const stockStatus = (product) => product.stock_quantity === 0
  ? ["Out of Stock", "stock-out"]
  : product.stock_quantity <= product.low_stock_threshold ? ["Low Stock", "stock-low"] : ["In Stock", "stock-in"];

export default function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [message, setMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [stockProduct, setStockProduct] = useState(null);
  const [stockMode, setStockMode] = useState("add");
  const [stockQuantity, setStockQuantity] = useState("");
  const [stockSubmitting, setStockSubmitting] = useState(false);
  const [stockError, setStockError] = useState("");

  useEffect(() => {
    let ignore = false;
    getProducts().then((data) => { if (!ignore) setProducts(data.products || []); })
      .catch((error) => { if (!ignore) setLoadError(error.message); })
      .finally(() => { if (!ignore) setLoading(false); });
    return () => { ignore = true; };
  }, []);

  const summary = useMemo(() => ({
    total: products.length,
    inStock: products.filter((p) => p.stock_quantity > p.low_stock_threshold).length,
    lowStock: products.filter((p) => p.stock_quantity > 0 && p.stock_quantity <= p.low_stock_threshold).length,
    outOfStock: products.filter((p) => p.stock_quantity === 0).length,
  }), [products]);

  function closeForm() { setFormOpen(false); setEditingId(null); setForm(EMPTY_FORM); setActionError(""); }
  function openAdd() { setEditingId(null); setForm(EMPTY_FORM); setActionError(""); setMessage(""); setFormOpen(true); }
  function openEdit(product) {
    setEditingId(product.product_id);
    setForm({ name: product.name, description: product.description || "", unit_name: product.unit_name, unit_price: String(product.unit_price), is_active: Boolean(product.is_active) });
    setActionError(""); setMessage(""); setFormOpen(true);
  }
  function changeForm(event) {
    const { name, value, type, checked } = event.target;
    setForm((current) => ({ ...current, [name]: type === "checkbox" ? checked : value }));
  }

  async function submitProduct(event) {
    event.preventDefault();
    const unitPrice = Number(form.unit_price);
    if (!form.name.trim() || !form.unit_name.trim() || form.unit_price === "") return setActionError("Product name, unit, and price per unit are required.");
    if (!Number.isFinite(unitPrice) || unitPrice < 0) return setActionError("Price per unit must be zero or greater.");
    setSubmitting(true); setActionError("");
    const payload = { name: form.name.trim(), description: form.description.trim() || null, unit_name: form.unit_name.trim(), unit_price: unitPrice, is_active: form.is_active };
    try {
      const saved = editingId === null ? await createProduct(payload) : await updateProduct(editingId, payload);
      setProducts((current) => editingId === null ? [saved, ...current] : current.map((p) => p.product_id === saved.product_id ? saved : p));
      setMessage(`${saved.name} was ${editingId === null ? "added" : "updated"} successfully.`); closeForm();
    } catch (error) { setActionError(error.message); } finally { setSubmitting(false); }
  }

  async function toggleActive(product) {
    setBusyId(product.product_id); setActionError("");
    try {
      const updated = await updateProduct(product.product_id, { is_active: !product.is_active });
      setProducts((current) => current.map((p) => p.product_id === updated.product_id ? updated : p));
      setMessage(`${updated.name} is now ${updated.is_active ? "active" : "inactive"}.`);
    } catch (error) { setActionError(error.message); } finally { setBusyId(null); }
  }

  async function removeProduct(product) {
    if (!window.confirm(`Delete ${product.name}? This action cannot be undone.`)) return;
    setBusyId(product.product_id); setActionError("");
    try { const result = await deleteProduct(product.product_id); setProducts((current) => current.filter((p) => p.product_id !== product.product_id)); setMessage(result.message); }
    catch (error) { setActionError(error.message); } finally { setBusyId(null); }
  }

  function openStock(product, mode) { setStockProduct(product); setStockMode(mode); setStockQuantity(mode === "set" ? String(product.stock_quantity) : ""); setStockError(""); }
  async function submitStock(event) {
    event.preventDefault(); const quantity = Number(stockQuantity);
    if (!Number.isInteger(quantity) || quantity < 0 || (stockMode === "add" && quantity === 0)) return setStockError(stockMode === "add" ? "Enter a positive whole number." : "Enter zero or a positive whole number.");
    setStockSubmitting(true);
    try {
      const updated = stockMode === "add" ? await addProductStock(stockProduct.product_id, quantity) : await setProductStock(stockProduct.product_id, quantity);
      setProducts((current) => current.map((p) => p.product_id === updated.product_id ? updated : p));
      setMessage(`${updated.name} stock is now ${updated.stock_quantity} ${updated.unit_name}${updated.stock_quantity === 1 ? "" : "s"}.`); setStockProduct(null);
    } catch (error) { setStockError(error.message); } finally { setStockSubmitting(false); }
  }

  return <>
    <section className="page-heading products-heading"><div><p className="eyebrow">Product catalogue</p><h1>Products &amp; Inventory</h1><p className="page-description">Manage your egg products, prices and availability.</p></div><button type="button" className="add-product-button" onClick={openAdd}>+ Add Product</button></section>
    <section className="inventory-summary" aria-label="Inventory summary"><article><span>Total Products</span><strong>{summary.total}</strong></article><article className="summary-in-stock"><span>In Stock</span><strong>{summary.inStock}</strong></article><article className="summary-low-stock"><span>Low Stock</span><strong>{summary.lowStock}</strong></article><article className="summary-out-stock"><span>Out of Stock</span><strong>{summary.outOfStock}</strong></article></section>
    {message && <p className="message success-message list-message" role="status">{message}</p>}{actionError && !formOpen && <p className="message error-message list-message">{actionError}</p>}
    <section className="inventory-panel panel" aria-labelledby="inventory-heading"><div className="inventory-panel-heading"><div><p className="eyebrow">Inventory</p><h2 id="inventory-heading">Your products</h2></div><span>{products.length} product{products.length === 1 ? "" : "s"}</span></div>
      {loading && <p className="state-message">Loading products…</p>}{!loading && loadError && <div className="state-message error-state"><strong>Products could not be loaded.</strong><span>{loadError}</span></div>}{!loading && !loadError && products.length === 0 && <div className="state-message empty-state"><strong>No products yet.</strong><span>Add your first product to begin managing inventory.</span></div>}
      {!loading && !loadError && products.length > 0 && <div className="product-inventory-grid">{products.map((product) => { const stock = stockStatus(product); const busy = busyId === product.product_id; return <article className="inventory-product-card" key={product.product_id}><div className="inventory-card-top"><div><h3>{product.name}</h3><p>{product.description || `Sold per ${product.unit_name}`}</p></div><span className={`status-badge ${product.is_active ? "active" : "inactive"}`}>{product.is_active ? "Active" : "Inactive"}</span></div><div className="inventory-metrics"><div><span>Unit</span><strong>{product.unit_name}</strong></div><div><span>Selling price</span><strong>{money.format(product.unit_price)}</strong></div><div><span>Current stock</span><strong>{Number(product.stock_quantity).toLocaleString()}</strong></div></div><div className="inventory-status-line"><span className={`stock-badge ${stock[1]}`}>{stock[0]}</span><small>Low-stock level: {product.low_stock_threshold}</small></div><div className="inventory-actions"><button type="button" onClick={() => openStock(product, "add")}>Add Stock</button><button type="button" className="secondary-button" onClick={() => openStock(product, "set")}>Set Stock</button><button type="button" className="secondary-button" onClick={() => openEdit(product)}>Edit Product</button><button type="button" className="secondary-button" disabled={busy} onClick={() => toggleActive(product)}>{product.is_active ? "Deactivate" : "Activate"}</button><button type="button" className="danger-button" disabled={busy} onClick={() => removeProduct(product)}>Delete</button></div></article>; })}</div>}
    </section>
    {formOpen && <div className="modal-backdrop" role="presentation"><form className="confirmation-dialog product-editor" role="dialog" aria-modal="true" aria-labelledby="product-editor-heading" onSubmit={submitProduct}><div className="dialog-title-row"><div><p className="eyebrow">Product details</p><h2 id="product-editor-heading">{editingId === null ? "Add Product" : "Edit Product"}</h2></div><button type="button" className="dialog-close" aria-label="Close" onClick={closeForm}>×</button></div><p className="form-example"><strong>Example:</strong> Egg · sold per egg · KES 20 per unit</p><label>Product Name<input name="name" value={form.name} onChange={changeForm} placeholder="e.g. Egg" required /></label><label>Description<textarea name="description" value={form.description} onChange={changeForm} rows="3" placeholder="Brief product description" /></label><div className="form-row"><label>Unit<input name="unit_name" value={form.unit_name} onChange={changeForm} placeholder="e.g. egg or tray" required /></label><label>Price Per Unit<div className="price-input"><span>KES</span><input name="unit_price" type="number" min="0" step="1" value={form.unit_price} onChange={changeForm} required /></div></label></div><label className="checkbox-label"><input name="is_active" type="checkbox" checked={form.is_active} onChange={changeForm} /><span><strong>Active product</strong><small>Available to customers when stock is present.</small></span></label>{actionError && <p className="message error-message">{actionError}</p>}<div className="dialog-actions"><button type="button" className="secondary-button" onClick={closeForm} disabled={submitting}>Cancel</button><button type="submit" disabled={submitting}>{submitting ? "Saving…" : "Save Product"}</button></div></form></div>}
    {stockProduct && <div className="modal-backdrop" role="presentation"><form className="confirmation-dialog stock-dialog" role="dialog" aria-modal="true" aria-labelledby="stock-heading" onSubmit={submitStock}><p className="eyebrow">Inventory update</p><h2 id="stock-heading">{stockMode === "add" ? "Add stock to" : "Set stock for"} {stockProduct.name}</h2><p>Current stock: <strong>{stockProduct.stock_quantity} {stockProduct.unit_name}{stockProduct.stock_quantity === 1 ? "" : "s"}</strong></p><label>{stockMode === "add" ? "Quantity received" : "New stock quantity"}<input type="number" min={stockMode === "add" ? "1" : "0"} step="1" value={stockQuantity} onChange={(event) => setStockQuantity(event.target.value)} required /></label>{stockError && <p className="message error-message">{stockError}</p>}<div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setStockProduct(null)} disabled={stockSubmitting}>Cancel</button><button type="submit" disabled={stockSubmitting}>{stockSubmitting ? "Updating…" : stockMode === "add" ? "Add Stock" : "Set Stock"}</button></div></form></div>}
  </>;
}
