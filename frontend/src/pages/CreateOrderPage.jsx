import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { placeCustomerOrder } from "../api/customerOrders.js";
import { cancelCustomerOrder } from "../api/customerPortal.js";
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
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [formError, setFormError] = useState("");
  const [orderResult, setOrderResult] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState("");
  const [cancelMessage, setCancelMessage] = useState("");

  useEffect(() => {
    let ignoreResult = false;

    async function loadProducts() {
      try {
        const data = await getProducts();
        if (!ignoreResult) {
          setProducts((data.products || []).filter((product) => product.is_active));
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
    setOrderResult(null);
    setCancelError("");
    setCancelMessage("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError("");
    setOrderResult(null);

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
    if (orderQuantity > selectedProduct.stock_quantity) {
      setFormError(`Only ${selectedProduct.stock_quantity} ${selectedProduct.unit_name}${selectedProduct.stock_quantity === 1 ? "" : "s"} are currently available.`);
      return;
    }

    setSubmitting(true);

    try {
      const result = await placeCustomerOrder({
        product_id: productId,
        quantity: orderQuantity,
      });
      setOrderResult(result);
      setProducts((current) => current.map((product) =>
        product.product_id === productId
          ? { ...product, stock_quantity: product.stock_quantity - orderQuantity }
          : product,
      ));
      setForm(EMPTY_FORM);
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCancelOrder() {
    if (!orderResult || orderResult.order_status !== "pending") {
      return;
    }

    const confirmed = window.confirm(
      "Are you sure you want to cancel this order?",
    );

    if (!confirmed) {
      return;
    }

    setCancelling(true);
    setCancelError("");
    setCancelMessage("");

    try {
      const updatedOrder = await cancelCustomerOrder(orderResult.order_id);
      setOrderResult((currentResult) => ({
        ...currentResult,
        order_status: updatedOrder.order_status,
      }));
      setProducts((current) => current.map((product) =>
        product.product_id === orderResult.product_id
          ? { ...product, stock_quantity: product.stock_quantity + orderResult.quantity }
          : product,
      ));
      setCancelMessage("Order cancelled successfully");
    } catch {
      setCancelError(
        "This order could not be cancelled. Its status may have already changed.",
      );
    } finally {
      setCancelling(false);
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
                        <option key={product.product_id} value={product.product_id} disabled={product.stock_quantity === 0}>
                          {product.name} — {formatAmount(product.unit_price)} / {product.unit_name} — {product.stock_quantity === 0 ? "Out of Stock" : `${product.stock_quantity} available`}
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
                      max={selectedProduct?.stock_quantity || undefined}
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
            <div>
              <dt>Available stock</dt>
              <dd>{selectedProduct ? `${selectedProduct.stock_quantity} ${selectedProduct.unit_name}${selectedProduct.stock_quantity === 1 ? "" : "s"}` : "—"}</dd>
            </div>
            <div className="summary-total">
              <dt>Total to Pay</dt>
              <dd>{formatAmount(estimatedTotal)}</dd>
            </div>
          </dl>

          {orderResult && (
            <div className="order-success" role="status">
              <strong>{orderResult.message}.</strong>
              <span>Order number: {orderResult.order_number}</span>
              <span>Total: {formatAmount(orderResult.total_amount)}</span>
              <span>
                Status:{" "}
                <span className={`status-badge status-${orderResult.order_status}`}>
                  {orderResult.order_status === "cancelled" ? "Cancelled" : "Pending"}
                </span>
              </span>
              {orderResult.order_status === "pending" && (
                <button
                  type="button"
                  className="danger-button"
                  onClick={handleCancelOrder}
                  disabled={cancelling}
                >
                  {cancelling ? "Cancelling order…" : "Cancel Order"}
                </button>
              )}
              {cancelError && (
                <p className="message error-message">{cancelError}</p>
              )}
              {cancelMessage && (
                <p className="message success-message">{cancelMessage}</p>
              )}
              <Link className="text-link" to="/customer/orders">View order status</Link>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}

export default CreateOrderPage;
