import { test, expect } from '@playwright/test';
import { formatDate } from '../src/utils/format.js';

const order = { order_id: 1, order_number: 'ORD-000001', products: 'Eggs × 2', quantity: 2, total_amount: 1000, order_status: 'processing', payment_status: 'unpaid', payment_method: 'mpesa', mpesa_status: 'pending', checkout_request_id: 'checkout-1', created_at: '2026-11-08 21:30:00' };

test('partial payment prompt shows remaining balance and sends an idempotency key', async ({ page }) => {
  await auth(page, 'customer');
  const partial = { ...order, payment_method: 'cash', mpesa_status: null, outstanding_amount: '400', has_payment_receipts: true };
  await page.route('**/api/customer/orders', route => route.fulfill({ json: { orders: [partial] } }));
  let sent;
  await page.route('**/api/payments/mpesa/stk-push', route => {
    sent = route.request().postDataJSON();
    return route.fulfill({ status: 202, json: { checkout_request_id: 'new-checkout', payment_status: 'pending' } });
  });
  await page.goto('/customer/orders');
  await page.getByRole('button', { name: 'Pay with M-Pesa' }).click();
  await expect(page.getByRole('heading', { name: /Pay.*400.*M-Pesa/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel Order', exact: true })).toBeHidden();
  await page.getByRole('button', { name: 'Send M-Pesa Prompt' }).click();
  await expect(page.getByText('Payment request sent.', { exact: false })).toBeVisible();
  expect(sent.order_id).toBe(1);
  expect(sent.request_key).toMatch(/^[0-9a-f-]{36}$/);
});

test('unknown initiation blocks payment retry and cash selection after reload', async ({ page }) => {
  await auth(page, 'customer');
  const unknown = { ...order, mpesa_status: null, checkout_request_id: null, payment_attempt_state: 'unknown' };
  await page.route('**/api/customer/orders', route => route.fulfill({ json: { orders: [unknown] } }));
  await page.goto('/customer/orders');
  for (let iteration = 0; iteration < 2; iteration++) {
    await expect(page.getByText('Payment in progress')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry M-Pesa' })).toBeHidden();
    await expect(page.getByRole('button', { name: 'Pay with Cash' })).toBeHidden();
    await expect(page.getByRole('button', { name: 'Check Payment Status' })).toBeDisabled();
    if (!iteration) await page.reload();
  }
});
async function auth(page, role) {
  await page.route('**/api/auth/me', route => route.fulfill({ json: { authenticated: true, role, user: { name: 'Test', phone_number: '0712345678' } } }));
  await page.route('**/api/admin/notifications*', route => route.fulfill({ json: { notifications: [], unread_count: 0 } }));
}

test('Nairobi display handles naive UTC and offset-aware production timestamps identically', () => {
  expect(formatDate('2026-11-08 21:30:00')).toEqual(formatDate('2026-11-09T00:30:00+03:00'));
  expect(formatDate('2026-11-08 21:30:00')).toContain('9 November 2026');
  expect(formatDate('2026-11-08 21:30:00')).toContain('EAT');
});

test('payment prompt disappears on confirmed payment and does not return after reload', async ({ page }) => {
  await auth(page, 'customer');
  let current = { ...order };
  await page.route('**/api/customer/orders', route => route.fulfill({ json: { orders: [current] } }));
  await page.goto('/customer/orders');
  await expect(page.getByText('Payment in progress')).toBeVisible();
  current = { ...order, payment_status: 'paid', order_status: 'completed', mpesa_status: 'successful' };
  await expect(page.getByText('Payment in progress')).toBeHidden({ timeout: 8000 });
  await expect(page.getByText('Payment successful.', { exact: true })).toBeVisible();
  await expect(page.getByText('Payment successful.', { exact: true })).toBeHidden({ timeout: 6000 });
  await page.reload();
  await expect(page.getByText('Payment in progress')).toBeHidden();
  await expect(page.getByText('Payment successful.', { exact: true })).toBeHidden();
});

test('order success consumes navigation state and expires without reappearing', async ({ page }) => {
  await auth(page, 'customer');
  await page.route('**/api/customer/orders', route => route.fulfill({ json: { orders: [{ ...order, payment_method: null, mpesa_status: null }] } }));
  await page.route('**/api/products', route => route.fulfill({ json: { products: [{ product_id: 1, name: 'Eggs', unit_name: 'tray', unit_price: 500 }] } }));
  await page.route('**/api/customer-orders', route => route.fulfill({ status: 201, json: { order_id: 1, order_number: 'ORD-000001' } }));
  await page.goto('/customer/order-now');
  await page.getByLabel('Choose Product').selectOption('1');
  await page.getByLabel('Quantity', { exact: false }).fill('2');
  await page.getByRole('button', { name: 'Order Now', exact: true }).click();
  await expect(page.getByText(/was placed successfully/)).toBeVisible();
  await expect(page.getByText(/was placed successfully/)).toBeHidden({ timeout: 6000 });
  await page.waitForTimeout(1500);
  await expect(page.getByText(/was placed successfully/)).toBeHidden();
  await page.reload();
  await expect(page.getByText(/was placed successfully/)).toBeHidden();
});

test('cancellation removes the active card and stays removed after refresh', async ({ page }) => {
  await auth(page, 'customer');
  let orders = [{ ...order, order_status: 'pending', payment_method: null, mpesa_status: null }];
  await page.route('**/api/customer/orders', route => route.fulfill({ json: { orders } }));
  await page.route('**/api/customer/orders/1/cancel', route => { orders = []; return route.fulfill({ json: { message: 'Order cancelled successfully' } }); });
  await page.goto('/customer/orders');
  page.on('dialog', d => d.accept());
  await page.getByRole('button', { name: 'Cancel Order', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'ORD-000001' })).toBeHidden();
  await page.reload();
  await expect(page.getByText('No orders yet.')).toBeVisible();
  await expect(page.getByText('Order cancelled successfully')).toBeHidden();
});

test('failed payment offers retry and its error can be dismissed', async ({ page }) => {
  await auth(page, 'customer');
  let current = { ...order };
  await page.route('**/api/customer/orders', route => route.fulfill({ json: { orders: [current] } }));
  await page.goto('/customer/orders');
  await expect(page.getByText('Payment in progress')).toBeVisible();
  current = { ...order, mpesa_status: 'failed' };
  await expect(page.getByRole('button', { name: 'Retry M-Pesa' })).toBeVisible({ timeout: 8000 });
  await page.getByRole('button', { name: 'Dismiss message' }).click();
  await expect(page.getByText(/M-Pesa payment failed/)).toBeHidden();
  await page.reload();
  await expect(page.getByText(/M-Pesa payment failed/)).toBeHidden();
});

test('mobile expense calculator saves server inputs and clears temporary success', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await auth(page, 'admin');
  let saved;
  const totals = { feed: '0', medicine: '0', total: '0' };
  await page.route('**/api/admin/expenses**', async route => {
    if (route.request().method() === 'POST') { saved = route.request().postDataJSON(); await route.fulfill({ status: 201, json: { id: 1, message: 'Expense saved successfully' } }); }
    else await route.fulfill({ json: { expenses: [], week: totals, month: totals } });
  });
  await page.goto('/admin/expenses?category=feed');
  await page.getByLabel('Feed Type').fill('Layers Mash');
  await page.getByLabel('Quantity (kg)').fill('50');
  await page.getByLabel('Price per kg (KES)').fill('65');
  await expect(page.locator('output')).toContainText('3,250.00');
  await page.getByRole('button', { name: 'Save Expense', exact: true }).click();
  await expect(page.getByText('Expense saved successfully')).toBeVisible();
  expect(saved.quantity).toBe('50');
  expect(saved.total_amount).toBeUndefined();
  expect(saved.submission_key.length).toBeGreaterThan(16);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/expenses-mobile.png', fullPage: true });
  await expect(page.getByText('Expense saved successfully')).toBeHidden({ timeout: 6000 });
});

test('financial overview shows six cards and requests selected period', async ({ page }) => {
  await auth(page, 'admin');
  const queries = [];
  await page.route('**/api/admin/reports/summary?**', route => { queries.push(new URL(route.request().url()).searchParams.get('period')); return route.fulfill({ json: { period: { from: '2026-11-01', to: '2026-11-30' }, summary: { paid_orders_amount: '45000', unpaid_orders_amount: '12000', confirmed_payments_received: '45000', feed_expenses: '8500', medicine_expenses: '2000', total_expenses: '10500', net_cash_balance: '34500' } } }); });
  await page.goto('/admin/reports');
  await expect(page.locator('.stat-card')).toHaveCount(6);
  await expect(page.getByText('Net Cash Balance', { exact: true })).toBeVisible();
  await page.getByLabel('Reporting period').selectOption('week');
  await expect.poll(() => queries.at(-1)).toBe('week');
  await page.screenshot({ path: 'test-results/reports-desktop.png', fullPage: true });
});

test('notification bell persists read state and opens the related order', async ({ page }) => {
  await auth(page, 'admin');
  let read = false;
  await page.route('**/api/admin/notifications**', route => {
    if (route.request().method() === 'PATCH') { read = true; return route.fulfill({ json: { message: 'Notification read' } }); }
    return route.fulfill({ json: { unread_count: read ? 0 : 1, notifications: [{ id: 1, title: 'New Order Received', description: 'ORD-000001 worth KES 1000', order_id: 1, created_at: '2026-11-09T12:00:00+00:00', read_at: read ? '2026-11-09T12:01:00+00:00' : null }] } });
  });
  await page.route('**/api/admin/expenses**', route => route.fulfill({ json: { expenses: [], week: { feed: 0, medicine: 0, total: 0 }, month: { feed: 0, medicine: 0, total: 0 } } }));
  await page.route('**/api/orders', route => route.fulfill({ json: { orders: [] } }));
  await page.route('**/api/orders/1', route => route.fulfill({ json: { ...order, customer: { name: 'Test', phone_number: '0712345678' }, items: [] } }));
  await page.goto('/admin/expenses');
  await page.getByRole('button', { name: 'Notifications (1)' }).click();
  await page.getByRole('button', { name: 'Mark as read', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Notifications (0)' })).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: 'Notifications (0)' }).click();
  await page.getByRole('link', { name: 'Open order', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'ORD-000001' })).toBeVisible();
});
