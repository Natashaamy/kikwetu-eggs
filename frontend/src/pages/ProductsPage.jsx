import { useEffect, useState } from "react";

import {
  addProductStock,
  createProduct,
  deleteProduct,
  getProducts,
  setProductStock,
  updateProduct,
} from "../api/products.js";

const EMPTY_FORM = {
  name: "",
  description: "",
  unit_name: "",
  unit_price: "",
  is_active: true,
};

function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingProductId, setDeletingProductId] = useState(null);
  const [editingProductId, setEditingProductId] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [formError, setFormError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [listError, setListError] = useState("");
  const [stockProduct, setStockProduct] = useState(null);
  const [stockQuantity, setStockQuantity] = useState("");
  const [stockSubmitting, setStockSubmitting] = useState(false);
  const [stockError, setStockError] = useState("");
  const [stockMode, setStockMode] = useState("add");

  useEffect(() => {
    let ignoreResult = false;

    async function loadProducts() {
      try {
        const data = await getProducts();
        if (!ignoreResult) {
          setProducts(data.products || []);
          setLoadError("");
        }
      } catch (error) {
        if (!ignoreResult) {
          setLoadError(error.message);
        }
      } finally {
        if (!ignoreResult) {
          setLoading(false);
        }
      }
    }

    loadProducts();

    return () => {
      ignoreResult = true;
    };
  }, []);

  function handleChange(event) {
    const { name, value, type, checked } = event.target;
    setForm((currentForm) => ({
      ...currentForm,
      [name]: type === "checkbox" ? checked : value,
    }));
  }

  function resetForm() {
    setForm(EMPTY_FORM);
    setEditingProductId(null);
    setFormError("");
  }

  function handleEdit(product) {
    setEditingProductId(product.product_id);
    setForm({
      name: product.name,
      description: product.description || "",
      unit_name: product.unit_name,
      unit_price: String(product.unit_price),
      is_active: Boolean(product.is_active),
    });
    setFormError("");
    setSuccessMessage("");
    setListError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleDelete(product) {
    const confirmed = window.confirm(
      `Delete ${product.name}? This action cannot be undone.`,
    );

    if (!confirmed) {
      return;
    }

    setDeletingProductId(product.product_id);
    setListError("");
    setSuccessMessage("");

    try {
      const result = await deleteProduct(product.product_id);
      setProducts((currentProducts) =>
        currentProducts.filter((item) => item.product_id !== product.product_id),
      );
      if (editingProductId === product.product_id) {
        resetForm();
      }
      setSuccessMessage(result.message);
    } catch (error) {
      setListError(error.message);
    } finally {
      setDeletingProductId(null);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError("");
    setSuccessMessage("");

    const name = form.name.trim();
    const unitName = form.unit_name.trim();
    const unitPrice = Number(form.unit_price);

    if (!name || !unitName || form.unit_price === "") {
      setFormError("Product Name, Unit, and Price Per Unit are required.");
      return;
    }

    if (!Number.isFinite(unitPrice) || unitPrice < 0) {
      setFormError("Price Per Unit must be a number that is zero or greater.");
      return;
    }

    setSubmitting(true);

    try {
      const productData = {
        name,
        description: form.description.trim() || null,
        unit_name: unitName,
        unit_price: unitPrice,
        is_active: form.is_active,
      };

      if (editingProductId !== null) {
        const updatedProduct = await updateProduct(editingProductId, productData);
        setProducts((currentProducts) =>
          currentProducts.map((product) =>
            product.product_id === updatedProduct.product_id ? updatedProduct : product,
          ),
        );
        setSuccessMessage(`${updatedProduct.name} was updated successfully.`);
      } else {
        const newProduct = await createProduct(productData);
        setProducts((currentProducts) => [newProduct, ...currentProducts]);
        setSuccessMessage(`${newProduct.name} was added successfully.`);
      }

      resetForm();
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStockSubmit(event) {
    event.preventDefault();
    const quantity = Number(stockQuantity);
    if (!Number.isInteger(quantity) || quantity < 0 || (stockMode === "add" && quantity === 0)) {
      setStockError(stockMode === "add"
        ? "Add quantity must be a positive whole number."
        : "Stock must be a whole number that is zero or greater.");
      return;
    }
    setStockSubmitting(true);
    setStockError("");
    try {
      const updated = stockMode === "add"
        ? await addProductStock(stockProduct.product_id, quantity)
        : await setProductStock(stockProduct.product_id, quantity);
      setProducts((current) => current.map((product) =>
        product.product_id === updated.product_id ? updated : product,
      ));
      setSuccessMessage(stockMode === "add"
        ? `${quantity} ${updated.unit_name}${quantity === 1 ? "" : "s"} added to ${updated.name}.`
        : `${updated.name} stock set to ${updated.stock_quantity}.`);
      setStockProduct(null);
      setStockQuantity("");
    } catch (error) {
      setStockError(error.message);
    } finally {
      setStockSubmitting(false);
    }
  }

  function stockStatus(product) {
    if (product.stock_quantity === 0) return ["Out of Stock", "stock-out"];
    if (product.stock_quantity <= product.low_stock_threshold) return ["Low Stock", "stock-low"];
    return ["In Stock", "stock-in"];
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Product catalogue</p>
          <h1>Products</h1>
          <p className="page-description">
            Add each product once, choose how it is sold, and set its price per unit.
          </p>
        </div>
        <div className="product-count" aria-label={`${products.length} products`}>
          <strong>{products.length}</strong>
          <span>{products.length === 1 ? "product" : "products"}</span>
        </div>
      </section>

      <div className="content-grid">
        <section className="panel form-panel" aria-labelledby="add-product-heading">
          <div className="panel-heading form-panel-heading">
            <p className="section-number">01</p>
            <div>
              <h2 id="add-product-heading">
                {editingProductId === null ? "Add a product" : "Edit product"}
              </h2>
              <p>
                {editingProductId === null
                  ? "Create one product and define the unit customers order."
                  : "Update this product's details and availability."}
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="product-form">
            <p className="form-example">
              <strong>Example:</strong> Product Name: Egg · Unit: egg · Price Per Unit: KES 20
            </p>

            <label>
              Product Name <span aria-hidden="true">*</span>
              <input
                name="name"
                value={form.name}
                onChange={handleChange}
                placeholder="e.g. Egg"
                required
              />
            </label>

            <label>
              Description
              <textarea
                name="description"
                value={form.description}
                onChange={handleChange}
                placeholder="Briefly describe this product"
                rows="3"
              />
            </label>

            <div className="form-row">
              <label>
                Unit <span aria-hidden="true">*</span>
                <input
                  name="unit_name"
                  value={form.unit_name}
                  onChange={handleChange}
                  placeholder="e.g. egg"
                  required
                />
              </label>

              <label>
                Price Per Unit <span aria-hidden="true">*</span>
                <div className="price-input">
                  <span>KES</span>
                  <input
                    name="unit_price"
                    type="number"
                    min="0"
                    step="1"
                    value={form.unit_price}
                    onChange={handleChange}
                    placeholder="20"
                    required
                  />
                </div>
                <small className="field-help">
                  Price for one {form.unit_name.trim() || "unit"}.
                </small>
              </label>
            </div>

            <label className="checkbox-label">
              <input
                name="is_active"
                type="checkbox"
                checked={form.is_active}
                onChange={handleChange}
              />
              <span>
                <strong>Active product</strong>
                <small>Customers can order this item.</small>
              </span>
            </label>

            {formError && <p className="message error-message">{formError}</p>}
            {successMessage && (
              <p className="message success-message">{successMessage}</p>
            )}

            <div className="form-actions">
              <button type="submit" disabled={submitting}>
                {submitting
                  ? editingProductId === null
                    ? "Adding product…"
                    : "Saving changes…"
                  : editingProductId === null
                    ? "Add Product"
                    : "Save Changes"}
              </button>
              {editingProductId !== null && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={resetForm}
                  disabled={submitting}
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </section>

        <section className="panel list-panel" aria-labelledby="product-list-heading">
          <div className="panel-heading">
            <p className="section-number">02</p>
            <div>
              <h2 id="product-list-heading">Current products</h2>
              <p>Products are shown newest first.</p>
            </div>
          </div>

          {loading && <p className="state-message">Loading products…</p>}

          {!loading && loadError && (
            <div className="state-message error-state">
              <strong>Products could not be loaded.</strong>
              <span>{loadError}</span>
            </div>
          )}

          {!loading && !loadError && products.length === 0 && (
            <div className="state-message empty-state">
              <strong>No products yet</strong>
              <span>Use the form to add your first product.</span>
            </div>
          )}

          {!loading && !loadError && products.length > 0 && (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Product</th>
                    <th>Unit</th>
                    <th>Price</th>
                    <th>Available Stock</th>
                    <th>Status</th>
                    <th><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <tr key={product.product_id}>
                      <td data-label="ID">#{product.product_id}</td>
                      <td data-label="Product">
                        <strong>{product.name}</strong>
                        <span className="product-description">
                          {product.description || "No description"}
                        </span>
                      </td>
                      <td data-label="Unit">{product.unit_name}</td>
                      <td data-label="Price" className="price-cell">
                        KES {Number(product.unit_price).toLocaleString()}
                      </td>
                      <td data-label="Stock">
                        <strong>{product.stock_quantity} {product.unit_name}{product.stock_quantity === 1 ? "" : "s"}</strong>
                        <span className={`stock-badge ${stockStatus(product)[1]}`}>{stockStatus(product)[0]}</span>
                      </td>
                      <td data-label="Status">
                        <span
                          className={`status-badge ${
                            product.is_active ? "active" : "inactive"
                          }`}
                        >
                          {product.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td data-label="Actions">
                        <div className="row-actions">
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => { setStockMode("add"); setStockProduct(product); setStockQuantity(""); setStockError(""); }}
                          >
                            Add Stock
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => { setStockMode("set"); setStockProduct(product); setStockQuantity(String(product.stock_quantity)); setStockError(""); }}
                          >
                            Set Stock
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => handleEdit(product)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="danger-button"
                            onClick={() => handleDelete(product)}
                            disabled={deletingProductId === product.product_id}
                          >
                            {deletingProductId === product.product_id
                              ? "Deleting…"
                              : "Delete"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {listError && (
            <p className="message error-message list-message">{listError}</p>
          )}
        </section>
      </div>

      {stockProduct && (
        <div className="modal-backdrop" role="presentation">
          <form className="confirmation-dialog stock-dialog" role="dialog" aria-modal="true" aria-labelledby="add-stock-heading" onSubmit={handleStockSubmit}>
            <p className="eyebrow">Inventory</p>
            <h2 id="add-stock-heading">{stockMode === "add" ? "Add stock for" : "Set stock for"} {stockProduct.name}</h2>
            <p>Current stock: <strong>{stockProduct.stock_quantity} {stockProduct.unit_name}{stockProduct.stock_quantity === 1 ? "" : "s"}</strong></p>
            <label>{stockMode === "add" ? "Add quantity" : "Set available stock to"}<input type="number" min={stockMode === "add" ? "1" : "0"} step="1" inputMode="numeric" value={stockQuantity} onChange={(event) => { setStockQuantity(event.target.value); setStockError(""); }} required /></label>
            <p className="stock-preview">New stock: <strong>{stockMode === "add" ? stockProduct.stock_quantity + (Number.isInteger(Number(stockQuantity)) && Number(stockQuantity) > 0 ? Number(stockQuantity) : 0) : (Number.isInteger(Number(stockQuantity)) && Number(stockQuantity) >= 0 ? Number(stockQuantity) : stockProduct.stock_quantity)} {stockProduct.unit_name}s</strong></p>
            {stockError && <p className="message error-message">{stockError}</p>}
            <div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setStockProduct(null)} disabled={stockSubmitting}>Cancel</button><button type="submit" disabled={stockSubmitting}>{stockSubmitting ? "Updating stock…" : stockMode === "add" ? "Add Stock" : "Update Stock"}</button></div>
          </form>
        </div>
      )}
    </>
  );
}

export default ProductsPage;
