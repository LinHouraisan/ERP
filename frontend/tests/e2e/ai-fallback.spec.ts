import { test, expect } from '@playwright/test';
import { fixture, login, query, recommendAndSubmit } from './helpers';
test('模型无凭证失败时仍可人工完成办理', async ({ page }) => {
  const account = fixture();
  await login(page, 'http://127.0.0.1:5175');
  await page.getByRole('button', { name: '新建套餐咨询' }).click();
  await query(page, account.number);
  await page.getByLabel('客户需求原文（可选 AI 辅助）').fill('月费低于一百元并保留宽带');
  await page.getByRole('button', { name: '辅助分析需求' }).click();
  await expect(page.getByText('ValueError：辅助不可用，请继续人工处理')).toBeVisible();
  await recommendAndSubmit(page);
  await expect(page.getByTestId('acceptance-status')).toHaveText('办理成功');
  await page.getByRole('button', { name: '结束接待', exact: true }).click();
});
