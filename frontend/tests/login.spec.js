import { test, expect } from '@playwright/test';

for (const [device, viewport] of [['desktop', { width: 1280, height: 800 }], ['mobile', { width: 390, height: 844 }]]) {
  test.describe(device, () => {
    test.use({ viewport });
    let signedIn;
    test.beforeEach(async ({ page }) => {
      signedIn = false;
      await page.route('**/api/auth/me', route => route.fulfill({ json: signedIn
        ? { authenticated: true, role: 'customer', user: { name: 'Test customer' } }
        : { authenticated: false } }));
      await page.route('**/api/customer/dashboard', route => route.fulfill({ json: {
        pending_orders: 0, completed_orders: 0, cancelled_orders: 0, unpaid_orders: 0,
        amount_outstanding: 0, total_amount_spent: 0, recent_orders: [],
      } }));
    });
    async function fill(page) {
      await page.goto('/login');
      await page.getByLabel('Name', { exact: true }).fill('Test customer');
      await page.getByLabel('Password', { exact: true }).fill('test-password');
    }
    const submit = page => page.getByRole('button', { name: 'Login', exact: true }).click();
    async function succeed(route) {
      signedIn = true;
      await route.fulfill({ json: { role: 'customer', user: { name: 'Test customer' } } });
    }

    test('network failure releases button and retry succeeds', async ({ page }) => {
      let calls = 0;
      await page.route('**/api/auth/login', route => ++calls === 1 ? route.abort('failed') : succeed(route));
      await fill(page); await submit(page);
      await expect(page.getByRole('alert')).toContainText('Unable to reach the server');
      await expect(page.getByRole('button', { name: 'Login', exact: true })).toBeEnabled();
      await submit(page);
      await expect(page).toHaveURL(/\/customer\/dashboard$/);
      expect(calls).toBe(2);
    });

    test('wrong credentials are temporary and allow retry', async ({ page }) => {
      await page.clock.install();
      await page.route('**/api/auth/login', route => route.fulfill({ status: 401, json: { error: 'Invalid name or password.' } }));
      await fill(page); await submit(page);
      await expect(page.getByRole('alert')).toHaveText('Invalid name or password.');
      await expect(page.getByRole('button', { name: 'Login', exact: true })).toBeEnabled();
      await page.clock.fastForward(8001);
      await expect(page.getByRole('alert')).toHaveCount(0);
      await submit(page);
      await expect(page.getByRole('alert')).toBeVisible();
    });

    test('unavailable backend gives a retryable error', async ({ page }) => {
      await page.route('**/api/auth/login', route => route.fulfill({ status: 503, contentType: 'text/html', body: 'Starting service' }));
      await fill(page); await submit(page);
      await expect(page.getByRole('alert')).toContainText('temporarily unavailable or waking up');
      await expect(page.getByRole('button', { name: 'Login', exact: true })).toBeEnabled();
    });

    test('pending request times out and permits retry', async ({ page }) => {
      await page.clock.install();
      let calls = 0;
      await page.route('**/api/auth/login', route => { if (++calls > 1) return succeed(route); });
      await fill(page); await submit(page);
      await expect(page.getByRole('button', { name: 'Please wait…', exact: true })).toBeDisabled();
      await page.clock.fastForward(60001);
      await expect(page.getByRole('alert')).toContainText('took too long');
      await expect(page.getByRole('button', { name: 'Login', exact: true })).toBeEnabled();
      await submit(page);
      await expect(page).toHaveURL(/\/customer\/dashboard$/);
    });

    test('delayed wake-up succeeds, session refresh and logout work', async ({ page }) => {
      await page.clock.install();
      let pending;
      await page.route('**/api/auth/login', route => { pending = route; });
      await page.route('**/api/auth/logout', route => {
        signedIn = false;
        return route.fulfill({ json: { message: 'Logged out' } });
      });
      await fill(page); await submit(page);
      await expect(page.getByRole('button', { name: 'Please wait…', exact: true })).toBeDisabled();
      await expect.poll(() => Boolean(pending)).toBe(true);
      await page.clock.fastForward(45000);
      await succeed(pending);
      await expect(page).toHaveURL(/\/customer\/dashboard$/);
      await page.reload();
      await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
      if (device === 'mobile') await page.getByRole('button', { name: 'Menu', exact: true }).click();
      await page.getByRole('button', { name: /Logout/ }).click();
      await expect(page).toHaveURL(/\/login$/);
      await page.reload();
      await expect(page.getByRole('button', { name: 'Login', exact: true })).toBeEnabled();
    });
  });
}
