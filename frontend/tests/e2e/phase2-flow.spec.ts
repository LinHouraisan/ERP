import { test, expect } from '@playwright/test';
import { login } from './helpers';

test.use({ actionTimeout: 10000 });

test('经营正常链路：报价、收款、出库、安装验收与收益', async ({ page }) => {
  test.setTimeout(120000);
  await login(page);
  const me = await (await page.request.get('/api/v1/auth/me')).json();
  const post = async (path: string, body: object) => {
    const response = await page.request.post('/api/v1'+path, { data: body, headers: { Origin: 'http://127.0.0.1:5174', 'X-CSRF-Token': me.csrf_token } });
    expect(response.ok(), `${path}: ${response.status()}`).toBeTruthy();
    return response.json();
  };
  const suffix = crypto.randomUUID().slice(0,8), name = '浏览器设备-'+suffix;
  const product = await post('/products', { name, kind: 'GOODS', tracking: 'SERIAL' });
  const policy = await post(`/products/${product.id}/policy-versions`, { valid_from: '2026-01-01', valid_to: '2099-12-31', monthly_fee: '0.00', one_time_fee: '199.99', contract_months: 0, broadband: null, source: '浏览器模拟检查', conditions: { verified_required: false, sale_discount: '0.09' } });
  await post(`/policy-versions/${policy.id}/publish`, {});
  const customer = await post('/customers', { display_name: '浏览器客户-'+suffix, contact: '', address: '模拟安装地址' });
  const supplier = await post('/inventory/suppliers', { name: '浏览器供应商-'+suffix, contact: '' });
  const purchase = await post('/inventory/purchases', { supplier_id: supplier.id, request_key: crypto.randomUUID(), lines: [{ product_id: product.id, quantity: 1, unit_cost: '100.00' }] });
  await post(`/inventory/purchases/${purchase.id}/approve`, {});
  await post(`/inventory/purchases/${purchase.id}/receive`, { request_key: crypto.randomUUID(), lines: [{ line_id: purchase.lines[0].id, quantity: 1, serials: ['BROWSER-'+suffix] }] });
  await page.goto('/sales?customer_id='+customer.id);
  await page.getByLabel('商品 / 有效政策', { exact: true }).fill(name);
  await page.getByText(name+' · 一次费 199.99 · 优惠 0.09 · V1', { exact: true }).click();
  await page.getByRole('button', { name: '生成订单并核算金额', exact: true }).click();
  await page.getByRole('button', { name: '核对金额并确认订单', exact: true }).click();
  await page.getByRole('button', { name: '提交模拟收款', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: '收款：已收款' })).toBeVisible();
  await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/dispatch') && r.request().method() === 'POST').then(r => expect(r.ok()).toBeTruthy()),
    page.getByRole('button', { name: '确认设备出库', exact: true }).click(),
  ]);
  await expect(page.getByRole('button', { name: '确认设备出库', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: '预约安装', exact: true }).click();
  await page.getByLabel('安装地址', { exact: true }).fill('演示市浏览器路 1 号');
  await page.getByLabel('预约时间（上海）', { exact: true }).fill('2026-10-04T10:00');
  await page.getByRole('button', { name: '创建安装预约', exact: true }).click();
  await page.getByLabel('装维人员', { exact: true }).click();
  await page.getByText('installer', { exact: true }).click();
  await page.getByRole('button', { name: /^派\s*工$/ }).click();
  for (const action of ['确认接单', '确认领料', '记录到场', '记录安装完成']) {
    await expect(page.getByRole('button', { name: action, exact: true })).toBeVisible();
    await page.getByLabel('本次处理记录', { exact: true }).fill('浏览器模拟：'+action);
    await page.getByRole('button', { name: action, exact: true }).click();
    await expect(page.getByRole('button', { name: action, exact: true })).toHaveCount(0);
  }
  await expect(page.getByRole('button', { name: '客户验收并完成工单', exact: true })).toBeVisible();
  await page.getByLabel('客户验收记录', { exact: true }).fill('模拟客户确认网络正常，仅用于演示验收');
  await page.getByLabel('已取得客户验收确认（演示操作需注明模拟）', { exact: true }).check();
  await page.getByRole('button', { name: '客户验收并完成工单', exact: true }).click();
  await expect(page.getByRole('button', { name: '计入安装收益台账', exact: true })).toBeVisible();
  await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/finance/accruals') && r.request().method() === 'POST').then(r => expect(r.ok()).toBeTruthy()),
    page.getByRole('button', { name: '计入安装收益台账', exact: true }).click(),
  ]);
  await page.goto('/customers?id='+customer.id);
  await expect(page.getByRole('cell', { name: '客户已验收', exact: true })).toBeVisible();
  await page.goto('/finance');
  await expect(page.getByText('收益与待结算提成', { exact: true })).toBeVisible();
  await page.goto('/operations');
  await expect(page.getByRole('cell', { name: '客户验收完成', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '基于当前快照生成摘要', exact: true }).click();
  await expect(page.getByText('摘要为辅助草稿；数字及引用已与快照核对，原因解释仍需人工确认。', { exact: true })).toBeVisible();
  await page.screenshot({ path: '../.local/e2e-phase2-operations.png', fullPage: true });
});
