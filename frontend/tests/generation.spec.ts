import {test,expect} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';
const root=path.resolve('..'),out=path.join(root,'reports/phase4');
const results=JSON.parse(fs.readFileSync(path.join(out,'live-files.json'),'utf8'));
const access=fs.readFileSync(path.join(root,'backend/data/teacher-access.txt'),'utf8').trim();
test('fresh real PDF questions appear on desktop tablet mobile, source and stage9',async({page})=>{
 await page.goto('/');await page.getByLabel('Mã truy cập giáo viên').fill(access);await page.getByRole('button',{name:'Vào không gian giáo viên'}).click();await expect(page.getByRole('heading',{name:/Hôm nay/})).toBeVisible();await expect(page.locator('.busy-banner')).toHaveCount(0);
 await page.getByRole('button',{name:'Thư viện bài học',exact:false}).click();
 await page.locator('.lesson-card').filter({hasText:'QA phase4 de-thi-hoc-ki'}).first().click();
 await expect(page.locator('.question-editor')).toHaveCount(6);await expect(page.locator('.pipeline-report')).toContainText('9.');
 await expect.poll(async()=>{const r=await page.request.get('/api/lessons/'+results.find((r:any)=>r.file.endsWith('.pdf')).lesson_id+'/generation-status');return (await r.json()).events[8].status;}).toBe('PASS');
 for(const [name,width,height] of [['desktop',1440,1000],['tablet',820,1180],['mobile',390,844]] as const){
  await page.setViewportSize({width,height});await expect(page.locator('.question-editor').first()).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await page.screenshot({path:path.join(out,'after-pdf-'+name+'.png'),fullPage:true});await page.locator('.questions-panel').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'viewport-pdf-'+name+'.png')});
 }
});
test('real provider503 retained draft can preview sources and retry without upload',async({page})=>{
 await page.goto('/');await page.getByLabel('Mã truy cập giáo viên').fill(access);await page.getByRole('button',{name:'Vào không gian giáo viên'}).click();await expect(page.getByRole('heading',{name:/Hôm nay/})).toBeVisible();await expect(page.locator('.busy-banner')).toHaveCount(0);
 await page.getByRole('button',{name:'Thư viện bài học',exact:false}).click();await page.locator('.lesson-card').filter({hasText:'QA phase4 Unit 6'}).first().click();
 await expect(page.locator('.source-tabs button')).toHaveCount(10);await expect(page.locator('.pipeline-report')).toBeVisible();
 await page.screenshot({path:path.join(out,'after-provider503-retained.png'),fullPage:true});
 const button=page.getByRole('button',{name:/Tạo.*bằng Gemini AI/,exact:false});await expect(button).toBeEnabled();
 let calls=0;await page.route('**/api/lessons/*/generate',async route=>{calls++;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{stage:5,reason_code:'TEST_PROVIDER_503',message:'Gemini đang quá tải (503). Bản nháp được giữ nguyên.'}})});});
 await button.click();await expect(page.getByRole('alert')).toContainText('Công đoạn 5');await expect(button).toBeEnabled();await expect(page.locator('.source-tabs button')).toHaveCount(10);expect(calls).toBe(1);
 await page.screenshot({path:path.join(out,'after-retry-error-detail.png'),fullPage:true});
});
