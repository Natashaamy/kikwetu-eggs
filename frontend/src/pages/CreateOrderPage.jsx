import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { placeCustomerOrder } from "../api/customerOrders.js";
import { getProducts } from "../api/products.js";
import { useAuth } from "../context/AuthContext.jsx";

const EMPTY_FORM = {
  product_id: "",
  quantity: "",
};

const currencyFormatter = new Intl.NumberFormat("en-KE", {
  style: "currency",
  currency: "KES",
  minimumFractionDigits: 0,
});

function formatAmount(amount) {
  return currencyFormatter.format(Number(amount || 0));
}

function CreateOrderPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [formError, setFormError] = useState("");

  useEffect(() => {
    let ignoreResult = false;

    async function loadProducts() {
      try {
        const data = await getProducts();
        if (!ignoreResult) {
          setProducts(data.products || []);
        }
      } catch {
        if (!ignoreResult) {
          setLoadError("Products could not be loaded. Please try again later.");
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

  const selectedProduct = useMemo(
    () =>
      products.find((product) => product.product_id === Number(form.product_id)) ||
      null,
    [form.product_id, products],
  );

  const quantity = Number(form.quantity);
  const estimatedTotal =
    selectedProduct && Number.isInteger(quantity) && quantity > 0
      ? Number(selectedProduct.unit_price) * quantity
      : 0;

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((currentForm) => ({ ...currentForm, [name]: value }));
    setFormError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError("");

    const productId = Number(form.product_id);
    const orderQuantity = Number(form.quantity);

    if (!selectedProduct || !Number.isInteger(productId)) {
      setFormError("Choose an available product.");
      return;
    }

    if (!Number.isInteger(orderQuantity) || orderQuantity <= 0) {
      setFormError("Quantity must be a positive whole number.");
      return;
    }
    setSubmitting(true);

    try {
      const result = await placeCustomerOrder({
        product_id: productId,
        quantity: orderQuantity,
      });
      navigate("/customer/orders", {
        replace: true,
        state: { newlyCreatedOrder: result },
      });
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  const noProducts = !loading && !loadError && products.length === 0;

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Fresh eggs, simple ordering</p>
          <h1>Order Now</h1>
          <p className="page-description">
            Choose a product and see your total before ordering.
          </p>
        </div>
      </section>

      <div className="create-order-grid">
        <section className="panel" aria-labelledby="order-form-heading">
          <div className="panel-heading">
            <p className="section-number">01</p>
            <div>
              <h2 id="order-form-heading">Place your order</h2>
              <p>Ordering as {user?.name}</p>
            </div>
          </div>

          {loading && <p className="state-message">Loading available products…</p>}

          {!loading && loadError && (
            <div className="state-message error-state">
              <strong>Products could not be loaded.</strong>
              <span>{loadError}</span>
            </div>
          )}

          {noProducts && (
            <div className="state-message empty-state">
              <strong>No active products are available.</strong>
              <span>Please check again later.</span>
            </div>
          )}

          {!loading && !loadError && products.length > 0 && (
            <form className="customer-order-form" onSubmit={handleSubmit}>
              <fieldset>
                <legend>Order Details</legend>
                <div className="form-row">
                  <label>
                    Choose Product <span aria-hidden="true">*</span>
                    <select
                      name="product_id"
                      value={form.product_id}
                      onChange={handleChange}
                      required
                    >
                      <option value="">Choose a product</option>
                      {products.map((product) => (
                        <option key={product.product_id} value={product.product_id}>
                          {product.name} — {formatAmount(product.unit_price)}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Quantity <span aria-hidden="true">*</span>
                    <input
                      name="quantity"
                      type="number"
                      min="1"
                      step="1"
                      inputMode="numeric"
                      value={form.quantity}
                      onChange={handleChange}
                      placeholder="e.g. 7"
                      required
                    />
                  </label>
                </div>
              </fieldset>

              {formError && <p className="message error-message">{formError}</p>}

              <button type="submit" disabled={submitting}>
                {submitting ? "Placing your order…" : "Order Now"}
              </button>
            </form>
          )}
        </section>

        <aside className="panel order-summary" aria-labelledby="order-summary-heading">
          <div className="panel-heading">
            <p className="section-number">02</p>
            <div>
              <h2 id="order-summary-heading">Your total</h2>
              <p>A live estimate using the current product price.</p>
            </div>
          </div>

          <dl className="summary-list">
            <div>
              <dt>Selected Product</dt>
              <dd>{selectedProduct?.name || "Not selected"}</dd>
            </div>
            <div>
              <dt>Unit price</dt>
              <dd>
                {selectedProduct
                  ? `${formatAmount(selectedProduct.unit_price)} / ${selectedProduct.unit_name}`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>Quantity</dt>
              <dd>{Number.isInteger(quantity) && quantity > 0 ? quantity : "—"}</dd>
            </div>
            {selectedProduct && Number.isInteger(quantity) && quantity > 0 && (
              <div className="calculation-line">
                <dt>Calculation</dt>
                <dd>{quantity} × {formatAmount(selectedProduct.unit_price)}</dd>
              </div>
            )}
            <div className="summary-total">
              <dt>Total to Pay</dt>
              <dd>{formatAmount(estimatedTotal)}</dd>
            </div>
          </dl>

        </aside>
      </div>
    </>
  );
}

export default CreateOrderPage;
