import { test, expect } from '@playwright/test';
import { login } from './helpers';

test.use({ actionTimeout:10000 });
test('售后页面审批、原设备退库、退款及组合净额',async({ page })=>{
  test.setTimeout(120000);
  await login(page);
  const me=await (await page.request.get('/api/v1/auth/me')).json();
  const post=async(path:string,body:object)=>{
    const r=await page.request.post('/api/v1'+path,{ data:body,headers:{ Origin:'http://127.0.0.1:5174','X-CSRF-Token':me.csrf_token } });
    expect(r.ok(),`${path}: ${r.status()}`).toBeTruthy();return r.json();
  };
  const suffix=crypto.randomUUID().slice(0,8),name='三期浏览器设备-'+suffix,serial='P3-UI-'+suffix;
  const product=await post('/products',{name,kind:'GOODS',tracking:'SERIAL'});
  const policy=await post(`/products/${product.id}/policy-versions`,{valid_from:'2026-01-01',valid_to:'2099-12-31',monthly_fee:'0.00',one_time_fee:'200.00',contract_months:0,broadband:null,source:'三期浏览器模拟政策',conditions:{verified_required:false}});
  await post(`/policy-versions/${policy.id}/publish`,{});
  const supplier=await post('/inventory/suppliers',{name:'三期浏览器供应商-'+suffix,contact:''});
  const purchase=await post('/inventory/purchases',{request_key:crypto.randomUUID(),supplier_id:supplier.id,lines:[{product_id:product.id,quantity:1,unit_cost:'100.00'}]});
  await post(`/inventory/purchases/${purchase.id}/approve`,{});
  await post(`/inventory/purchases/${purchase.id}/receive`,{request_key:crypto.randomUUID(),lines:[{line_id:purchase.lines[0].id,quantity:1,serials:[serial]}]});
  const customer=await post('/customers',{display_name:'三期浏览器客户-'+suffix,address:'模拟地址'});
  const order=await post('/sales/orders',{request_key:crypto.randomUUID(),customer_id:customer.id,lines:[{policy_version_id:policy.id,quantity:1}]});
  for(const [action,body] of [['confirm',{}],['pay',{method:'CARD'}],['dispatch',{}]] as const) await post(`/sales/orders/${order.id}/${action}`,body);
  const tx=await post('/transactions',{request_key:crypto.randomUUID(),customer_id:customer.id,title:'浏览器售后组合-'+suffix,required:['SALE'],order_ids:[order.id]});
  await page.goto('/aftersales?order_id='+order.id);
  await page.getByLabel('售后方式',{exact:true}).click();
  await page.getByText('已交付商品退货退款',{exact:true}).click();
  await page.getByLabel('原单商品或服务',{exact:true}).click();
  await page.getByText(name+' · 剩余可退 200.00 元 / 1 件',{exact:true}).click();
  await page.getByLabel('本次退款金额',{exact:true}).fill('100.00');
  await page.getByLabel('商品退回或取消数量（服务填 0）',{exact:true}).fill('1');
  await page.getByLabel('申请原因',{exact:true}).fill('浏览器模拟部分退货-'+suffix);
  await page.getByRole('button',{name:'提交售后申请',exact:true}).click();
  await page.getByLabel('审批依据',{exact:true}).fill('已核对原收款及退货申请');
  await page.getByRole('button',{name:'提交审批',exact:true}).click();
  await page.getByLabel(name+' · 退回 1 台的原序列号',{exact:true}).fill(serial);
  await page.getByLabel('验收情况',{exact:true}).fill('原序列号核对无误，模拟验收');
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/receive')&&r.request().method()==='POST').then(r=>expect(r.ok()).toBeTruthy()),page.getByRole('button',{name:'确认退货入库',exact:true}).click()]);
  await page.getByRole('button',{name:'提交模拟退款',exact:true}).click();
  await page.getByLabel('结案依据',{exact:true}).fill('退款与实物均已核实');
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/close')&&r.request().method()==='POST').then(r=>expect(r.ok()).toBeTruthy()),page.getByRole('button',{name:'核对退款与实物后结案',exact:true}).click()]);
  await page.goto('/transactions?id='+tx.id);
  await expect(page.getByText('已完成（含售后或调整） · 原金额 200.00 元 · 已退 100.00 元 · 净收 100.00 元',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'打开子单',exact:true})).toHaveAttribute('href','/sales?id='+order.id);
  await page.screenshot({path:'../.local/e2e-phase3-transaction.png',fullPage:true});
  for(const [path,title] of [['/settlements','分批提成结算'],['/transfers','两店调拨'],['/reversals','通信冲正'],['/todos','统一待办']] as const){
    await page.goto(path);await expect(page.getByText(title,{exact:true}).first()).toBeVisible();await expect(page.locator('.ant-alert-error')).toHaveCount(0);
  }
});

test('两店页面调出、短到差异和后续补收',async({page})=>{
  test.setTimeout(120000);await login(page);
  let auth=await (await page.request.get('/api/v1/auth/me')).json();
  const post=async(path:string,body:object)=>{
    const r=await page.request.post('/api/v1'+path,{data:body,headers:{Origin:'http://127.0.0.1:5174','X-CSRF-Token':auth.csrf_token}});
    expect(r.ok(),`${path}: ${r.status()}`).toBeTruthy();return r.json();
  };
  const switchUser=async(username:string)=>{auth=await post('/auth/login',{username,password:process.env.DEMO_PASSWORD!});};
  const suffix=crypto.randomUUID().slice(0,8),name='三期调拨耗材-'+suffix,sku='UI-'+suffix.toUpperCase();
  const product=await post('/products',{name,sku,kind:'GOODS',tracking:'QUANTITY'});
  await switchUser('admin2');await post('/products',{name,sku,kind:'GOODS',tracking:'QUANTITY'});await switchUser('admin');
  const supplier=await post('/inventory/suppliers',{name:'三期调拨供货-'+suffix});
  const po=await post('/inventory/purchases',{request_key:crypto.randomUUID(),supplier_id:supplier.id,lines:[{product_id:product.id,quantity:2,unit_cost:'10.00'}]});
  await post(`/inventory/purchases/${po.id}/approve`,{});
  await post(`/inventory/purchases/${po.id}/receive`,{request_key:crypto.randomUUID(),lines:[{line_id:po.lines[0].id,quantity:2,serials:[]}]});
  await page.goto('/transfers');
  await page.getByLabel('调入门店',{exact:true}).click();await page.getByText('模拟营业厅二店',{exact:true}).click();
  await page.getByLabel('本店商品',{exact:true}).fill(name);await page.getByText(name+' · '+sku,{exact:true}).click();
  await page.getByLabel('调拨数量',{exact:true}).fill('2');await page.getByLabel('调拨原因',{exact:true}).fill('模拟二店调拨浏览器验收');
  await page.getByRole('button',{name:'提交调拨申请',exact:true}).click();
  await page.getByLabel('审批依据',{exact:true}).fill('已核对二店需求');await page.getByRole('button',{name:'审核调拨',exact:true}).click();
  await page.getByLabel('发货交运记录',{exact:true}).fill('模拟两件已交运');
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/dispatch')&&r.request().method()==='POST').then(r=>expect(r.ok()).toBeTruthy()),page.getByRole('button',{name:'确认调出并记在途',exact:true}).click()]);
  const url=page.url();await switchUser('admin2');await page.goto(url);
  await page.getByLabel('本次实际到货数量',{exact:true}).fill('1');await page.getByLabel('验收记录（含短少或错货情况）',{exact:true}).fill('模拟首批只到一件');
  await page.getByRole('button',{name:'登记到货与差异',exact:true}).click();
  await expect(page.getByText('2 / 1 / 1 / 0',{exact:true})).toBeVisible();
  await page.getByLabel('验收记录（含短少或错货情况）',{exact:true}).fill('模拟后续补到剩余一件');await page.getByRole('button',{name:'登记到货与差异',exact:true}).click();
  await expect(page.getByText('2 / 2 / 0 / 0',{exact:true})).toBeVisible();
  await expect(page.locator('.ant-alert-error')).toHaveCount(0);
  await page.screenshot({path:'../.local/e2e-phase3-transfer.png',fullPage:true});
});
