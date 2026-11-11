import {test,expect} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';
const root=path.resolve('..'),out=path.join(root,'reports/production');
const access=fs.readFileSync(path.join(root,'backend/data/teacher-access.txt'),'utf8').trim();
async function login(page:any){await page.goto('/');await page.getByLabel('Mã truy cập giáo viên').fill(access);await page.getByRole('button',{name:'Vào không gian giáo viên'}).click();await expect(page.getByRole('heading',{name:/Hôm nay/})).toBeVisible();await expect(page.locator('.busy-banner')).toHaveCount(0);}

test('HTTPS proxy login uses secure cookie, cannot read private results anonymously',async({page,context,browser})=>{
 test.skip(process.env.ADVENTURE_E2E_TLS!=='1','HTTPS rehearsal only');
 await login(page);const cookies=await context.cookies();const teacher=cookies.find(c=>c.name==='teacher_session');expect(teacher?.secure).toBe(true);expect(teacher?.httpOnly).toBe(true);expect(teacher?.path).toBe('/api');expect(await page.evaluate(()=>document.cookie.includes('teacher_session'))).toBe(false);
 await page.screenshot({path:path.join(out,'https-teacher-dashboard.png'),fullPage:true});
 const anonymous=await browser.newContext({ignoreHTTPSErrors:true});const response=await anonymous.request.get(process.env.ADVENTURE_E2E_URL+'/api/results');expect(response.status()).toBe(401);await anonymous.close();
});

test('real 70MB PPTX uploads in 2MB parts through HTTPS proxy and durable extraction job',async({page})=>{
 test.skip(process.env.ADVENTURE_E2E_TLS!=='1','HTTPS rehearsal only');
 test.setTimeout(120000);await login(page);let parts=0,jobs=0;const before=JSON.parse(fs.readFileSync(path.join(out,'proxy-metrics.json'),'utf8')).chunks.length;
 page.on('request',r=>{if(r.method()==='PUT'&&r.url().includes('/api/uploads/')){parts++;}if(r.url().includes('/api/jobs/'))jobs++;});
 await page.getByRole('button',{name:'Tạo bài học',exact:true}).click();
 const uploadPath=path.join(root,'.cache','QA production transport.pptx');fs.mkdirSync(path.dirname(uploadPath),{recursive:true});fs.copyFileSync(path.join(root,'input/Unit 6 Lesson 2 Period 3.pptx'),uploadPath);await page.getByLabel('Tải tài liệu mới',{exact:true}).setInputFiles(uploadPath);
 await expect(page.getByRole('heading',{name:'Không gian kiểm duyệt'})).toBeVisible({timeout:90000});await expect(page.locator('.source-tabs button')).toHaveCount(10);const chunks=JSON.parse(fs.readFileSync(path.join(out,'proxy-metrics.json'),'utf8')).chunks.slice(before);const maxBytes=Math.max(...chunks.map((c:any)=>c.bytes));expect(chunks).toHaveLength(parts);expect(chunks.reduce((sum:number,c:any)=>sum+c.bytes,0)).toBe(70396372);expect(parts).toBeGreaterThan(30);expect(maxBytes).toBeGreaterThan(0);expect(maxBytes).toBeLessThanOrEqual(2*1024*1024);expect(jobs).toBeGreaterThan(0);
 await page.screenshot({path:path.join(out,'https-upload-real-pptx.png'),fullPage:true});await page.screenshot({path:path.join(out,'https-upload-viewport.png')});
 fs.writeFileSync(path.join(out,'https-upload.json'),JSON.stringify({status:'PASS',source:'real input PPTX',bytes:fs.statSync(path.join(root,'input/Unit 6 Lesson 2 Period 3.pptx')).size,parts,max_chunk_bytes:maxBytes,job_polls:jobs,slides:10},null,2));
});

test('browser resumes saved job after refresh without submitting AI a second time',async({page})=>{
 test.skip(process.env.ADVENTURE_E2E_TLS!=='1','HTTPS rehearsal only');
 await login(page);const list=await (await page.request.get('/api/lessons')).json();const lesson=list.find((l:any)=>l.title.startsWith('QA phase4 de-thi-hoc-ki'));
 expect(lesson).toBeTruthy();let submissions=0,polls=0,finish=false;
 await page.route('**/api/lessons/*/generate',async route=>{submissions++;expect(route.request().headers()['prefer']).toBe('respond-async');expect(route.request().headers()['idempotency-key']).toBeTruthy();await route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({job_id:'browser-recovery-fixture',state:'queued'})});});
 await page.route('**/api/jobs/browser-recovery-fixture',async route=>{polls++;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(finish?{job_id:'browser-recovery-fixture',state:'succeeded',result:{...lesson,generation:{cached:true}}}:{job_id:'browser-recovery-fixture',state:'running'})});});
 await page.getByRole('button',{name:'Thư viện bài học',exact:false}).click();await page.locator('.lesson-card').filter({hasText:'QA phase4 de-thi-hoc-ki'}).first().click();await page.getByRole('button',{name:/Tạo.*bằng Gemini AI/}).click();await expect.poll(()=>polls).toBeGreaterThan(0);
 await expect.poll(()=>page.evaluate(()=>localStorage.getItem('adventure.pendingJob'))).toBe('browser-recovery-fixture');await page.reload();finish=true;
 await expect(page.getByRole('heading',{name:'Không gian kiểm duyệt'})).toBeVisible();await expect(page.locator('.question-editor')).toHaveCount(6);expect(submissions).toBe(1);await expect.poll(()=>page.evaluate(()=>localStorage.getItem('adventure.pendingJob'))).toBe(null);
 await page.screenshot({path:path.join(out,'https-job-resumed.png'),fullPage:true});
});


test('anonymous student can load published image and finish quiz over HTTPS proxy',async({browser})=>{
 test.skip(process.env.ADVENTURE_E2E_TLS!=='1','HTTPS rehearsal only');
 const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});const page=await context.newPage();
 await page.goto(process.env.ADVENTURE_E2E_URL+'/#/play/1410BBC7');await page.getByRole('button',{name:/Quiz Challenge/}).click();
 const image=page.locator('.student-question-media img');await expect(image).toBeVisible();await expect.poll(()=>image.evaluate(el=>(el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
 await page.screenshot({path:path.join(out,'https-anonymous-student.png')});await page.locator('.answer-options').getByRole('button').filter({hasText:'Three'}).click();await expect(page.locator('.feedback')).toContainText('Great job!');await page.locator('.feedback button').click();await expect(page.locator('.result-medal')).toContainText('100');
 expect((await context.cookies()).some(c=>c.name==='teacher_session')).toBe(false);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await context.close();
});


test('HTML proxy timeout is explained and draft source stays visible',async({page})=>{
 test.skip(process.env.ADVENTURE_E2E_TLS!=='1','HTTPS rehearsal only');await login(page);
 await page.getByRole('button',{name:'Thư viện bài học',exact:false}).click();await page.locator('.lesson-card').filter({hasText:'QA phase4 de-thi-hoc-ki'}).first().click();
 await page.route('**/api/lessons/*/generate',r=>r.fulfill({status:504,contentType:'text/html',body:'<html>Gateway timeout</html>'}));
 await page.getByRole('button',{name:/Tạo.*bằng Gemini AI/}).click();await expect(page.getByRole('alert')).toContainText('HTTP 504');await expect(page.locator('.source-tabs button')).toHaveCount(6);await expect(page.getByRole('button',{name:/Tạo.*bằng Gemini AI/})).toBeEnabled();
});
