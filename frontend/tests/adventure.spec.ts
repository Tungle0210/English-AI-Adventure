import {test,expect,Page} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve('..');
const teacherCode=fs.readFileSync(path.join(root,'backend/data/teacher-access.txt'),'utf8').trim();
const live=JSON.parse(fs.readFileSync(path.join(root,'reports/phase2-live.json'),'utf8'));
const screenshots=path.join(root,'reports/screenshots');fs.mkdirSync(screenshots,{recursive:true});
async function login(page:Page){await page.goto('/');await page.getByLabel('Mã truy cập giáo viên').fill(teacherCode);await page.getByRole('button',{name:'Vào không gian giáo viên'}).click();await expect(page.getByRole('heading',{name:/Hôm nay/})).toBeVisible();await expect(page.locator('.busy-banner')).toHaveCount(0);}
async function noOverflow(page:Page){expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);}

test('teacher edits real Gemini output, reviews, publishes; student completes all five games',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await login(page);
 await page.request.post('/api/lessons/'+live.lesson_id+'/unpublish');await page.reload();await expect(page.getByRole('heading',{name:/Hôm nay/})).toBeVisible();
 await page.screenshot({path:path.join(screenshots,'teacher-dashboard-desktop.png'),fullPage:true});
 await page.getByRole('button',{name:'Thư viện bài học',exact:false}).click();
 const card=page.locator('.lesson-card').filter({hasText:'Unit 6 Lesson 2 Period 3'}).first();await card.click();
 await expect(page.getByRole('heading',{name:'Không gian kiểm duyệt'})).toBeVisible();
 const q=page.locator('.question-editor');expect(await q.count()).toBe(6);
 // Human review found unaccented Vietnamese and a listening question without
 // the spoken answer. Correct these before approving, using the real editor.
 const translations=[['trường học','lớp học','sân chơi'],[],['thị trấn'],['tòa nhà']];
 for(let i=0;i<4;i++){
  const card=q.nth(i);const kind=await card.getByRole('combobox',{name:'Hoạt động',exact:true}).inputValue();
  if(kind==='vocabulary'||kind==='match'){
   await card.getByLabel('Nghĩa tiếng Việt',{exact:true}).fill(translations[i][0]);
   await card.getByLabel('Đáp án đúng',{exact:true}).fill(translations[i][0]);
   if(kind==='vocabulary')await card.getByLabel('Lựa chọn (mỗi dòng một đáp án)').fill(translations[i].join('\n'));
   if(kind==='vocabulary')await card.getByRole('combobox',{name:'Minh họa từ vựng',exact:true}).selectOption('school');
  }
 }
 await q.nth(4).getByLabel('Nội dung đọc tiếng Anh').fill('There are three buildings at Bill’s school.');
 const explanations=['School có nghĩa là trường học.','Nguồn cho biết trường của Bill ở thị trấn.','Town có nghĩa là thị trấn.','Building có nghĩa là tòa nhà.','Nguồn nói có ba tòa nhà tại trường của Bill.','Where’s là dạng rút gọn của Where is.'];
 for(let i=0;i<6;i++)await q.nth(i).getByRole('textbox',{name:'Giải thích',exact:true}).fill(explanations[i]);
 // Agent checked the generated facts against actual source. Exercise a teacher edit,
 // then save; changed question must return to pending approval.
 const explanation=q.first().getByRole('textbox',{name:'Giải thích',exact:true});await explanation.fill((await explanation.inputValue())+' Giáo viên đã đối chiếu nguồn.');
 await page.getByRole('button',{name:/Lưu thay đổi/}).click();await expect(page.getByRole('status')).toContainText('Đã lưu');
 for(const checkbox of await page.locator('.approval-check input').all())await checkbox.check();
 await page.getByRole('button',{name:/Lưu thay đổi/}).click();await expect(page.locator('.question-editor.approved')).toHaveCount(6);
 await page.getByRole('button',{name:'Xuất bản',exact:true}).click();await expect(page.locator('.share-panel')).toBeVisible();
 await page.screenshot({path:path.join(screenshots,'teacher-review-desktop.png'),fullPage:true});
 const published=await (await page.request.get('/api/lessons/'+live.lesson_id)).json();
 fs.writeFileSync(path.join(root,'reports/browser-published-lesson.json'),JSON.stringify(published,null,2));
 await page.getByRole('link',{name:'Mở bài học'}).click();await expect(page.getByRole('heading',{name:published.title})).toBeVisible();await noOverflow(page);
 await page.screenshot({path:path.join(screenshots,'student-map-desktop.png'),fullPage:true});
 await page.getByRole('button',{name:/Bắt đầu hành trình/}).click();
 const answers:Record<string,string>=Object.fromEntries(published.questions.map((q:any)=>[q.id,q.answer]));
 const byPrompt=Object.fromEntries(published.questions.map((q:any)=>[q.prompt,q]));
 for(let i=0;i<published.questions.length;i++){
  const prompt=await page.locator('.play-question').innerText();const current=byPrompt[prompt];expect(current).toBeTruthy();
  if(current.kind==='fill'){await page.getByLabel('Từ còn thiếu là…').fill(answers[current.id]);await page.getByRole('button',{name:'Kiểm tra',exact:true}).click();}
  else if(current.kind==='match'){await page.locator('.matching-board>div').nth(1).getByRole('button',{name:answers[current.id],exact:true}).click();}
  else {await page.locator('.answer-options').getByRole('button').filter({hasText:answers[current.id]}).click();}
  await expect(page.locator('.feedback')).toContainText('Great job!');
  if(i===0)await page.screenshot({path:path.join(screenshots,'student-game-desktop.png'),fullPage:true});
  await page.locator('.feedback').getByRole('button').click();
 }
 await expect(page.getByRole('heading',{name:'Em đã làm được rồi!'})).toBeVisible();await expect(page.locator('.result-medal')).toContainText('100');
 await page.screenshot({path:path.join(screenshots,'student-result-desktop.png'),fullPage:true});
 await page.getByRole('link',{name:'Giáo viên',exact:false}).click();await page.getByRole('button',{name:'Kết quả học sinh',exact:true}).click();await expect(page.locator('.result-row').first()).toContainText('Hoàn thành');
 await page.screenshot({path:path.join(screenshots,'teacher-results-desktop.png'),fullPage:true});expect(errors).toEqual([]);
});

test('responsive desktop tablet mobile and speech fallback',async({page})=>{
 await login(page);
 for(const [name,width,height] of [['desktop',1440,1000],['tablet',768,1024],['mobile',390,844]] as const){await page.setViewportSize({width,height});await noOverflow(page);await page.screenshot({path:path.join(screenshots,`teacher-dashboard-${name}.png`),fullPage:true});}
 const published=JSON.parse(fs.readFileSync(path.join(root,'reports/browser-published-lesson.json'),'utf8'));
 await page.addInitScript(()=>{Object.defineProperty(window,'speechSynthesis',{value:undefined,configurable:true});Object.defineProperty(window,'SpeechSynthesisUtterance',{value:undefined,configurable:true});});
 await page.goto('/?speech-fallback-test=1#/play/'+published.code);await expect(page.getByRole('heading',{name:published.title})).toBeVisible();
 for(const [name,width,height] of [['desktop',1440,1000],['tablet',768,1024],['mobile',390,844]] as const){await page.setViewportSize({width,height});await noOverflow(page);await page.screenshot({path:path.join(screenshots,`student-map-${name}.png`),fullPage:true});}
 await page.getByRole('button',{name:/Listen & Choose/}).click();await expect(page.getByRole('status')).toContainText('chưa hỗ trợ giọng đọc');await page.getByRole('button',{name:'Không nghe được? Mở bản chữ'}).click();await expect(page.locator('.transcript')).toBeVisible();await noOverflow(page);await page.screenshot({path:path.join(screenshots,'student-listen-mobile.png'),fullPage:true});
});

test('invalid code, missing connection, invalid upload are visible',async({page})=>{
 await page.goto('/#/play');await page.getByLabel('Mã bài học của em').fill('INVALID');await page.getByRole('button',{name:'Khám phá',exact:true}).click();await expect(page.getByRole('alert')).toContainText('chưa đúng');
 await page.route('**/api/play/NETWORK',route=>route.abort());await page.getByLabel('Mã bài học của em').fill('NETWORK');await page.getByRole('button',{name:'Khám phá',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Mất kết nối');
 await login(page);await page.getByRole('button',{name:'Tạo bài học',exact:true}).click();await page.getByLabel('Tải tài liệu mới',{exact:true}).setInputFiles({name:'fake.pptx',mimeType:'application/octet-stream',buffer:Buffer.from('not a pptx')});await expect(page.getByRole('alert')).toContainText('Không đọc được');
});

test('editor and navigation on touch sizes; microphone-free speech fallback preserves play',async({page})=>{
 await login(page);
 await page.setViewportSize({width:390,height:844});
 await expect(page.locator('.sidebar')).toBeHidden();
 await page.getByRole('button',{name:'Mở menu'}).click();await expect(page.locator('.sidebar')).toBeVisible();
 await page.getByRole('button',{name:'Thư viện bài học',exact:false}).click();await expect(page.locator('.sidebar')).toBeHidden();
 await page.locator('.lesson-card').filter({has:page.getByRole('heading',{name:'Our school facilities',exact:true})}).click();
 await expect(page.getByRole('heading',{name:'Không gian kiểm duyệt'})).toBeVisible();await noOverflow(page);
 await page.screenshot({path:path.join(screenshots,'teacher-review-mobile.png'),fullPage:true});
 // Check the hero's text box is actually within its clipped panel, not merely
 // within the document scroll width.
 await page.getByRole('button',{name:'Mở menu'}).click();await page.getByRole('button',{name:'Tổng quan',exact:true}).click();
 const bounds=await page.locator('.hero').evaluate(el=>{const hero=el.getBoundingClientRect();const h=el.querySelector('h2')!.getBoundingClientRect();return {left:h.left,right:h.right,heroLeft:hero.left,heroRight:hero.right};});
 expect(bounds.left).toBeGreaterThanOrEqual(bounds.heroLeft);expect(bounds.right).toBeLessThanOrEqual(bounds.heroRight);
});
