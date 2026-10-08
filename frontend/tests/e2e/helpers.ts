import { expect, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
export function fixture(scenario = 'NORMAL') {
  const python = resolve(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python');
  return JSON.parse(execFileSync(python, ['-m','tests.e2e_fixture', scenario], { cwd: resolve('../backend'), encoding: 'utf-8' })) as { number: string; account_id: string };
}
export async function login(page: Page, origin = 'http://127.0.0.1:5174') {
  await page.goto(origin + '/services');
  await page.getByLabel('用户名', { exact: true }).fill('admin');
  const password = page.getByLabel('口令', { exact: true });
  try {
    await password.fill(process.env.DEMO_PASSWORD!);
    await page.getByRole('button', { name: /^登\s*录$/ }).click({ timeout: 10000 });
    await expect(page.getByRole('button', { name: '新建套餐咨询' })).toBeVisible();
  } finally {
    if (await password.isVisible()) await password.clear();
  }
}
export async function query(page: Page, number: string) {
  await page.getByLabel('模拟号码', { exact: true }).fill(number);
  await page.getByRole('button', { name: '查询账号资料', exact: true }).click();
  await expect(page.getByText('资料完整', { exact: true })).toBeVisible();
}
export async function recommendAndSubmit(page: Page) {
  await page.getByRole('button', { name: '生成规则方案' }).click();
  await page.getByTestId('candidate-89.00').getByRole('button', { name: '质检此方案' }).click();
  await page.getByLabel('复核原因', { exact: true }).fill('核对费用、合约及宽带，客户已了解');
  await page.getByRole('button', { name: '保存人工复核' }).click();
  await page.getByRole('button', { name: '建立受理草稿' }).click();
  await page.getByRole('button', { name: '确认并提交模拟办理' }).click();
}
