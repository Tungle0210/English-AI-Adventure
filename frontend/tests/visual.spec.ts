import {test,expect,Page} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';
const root=path.resolve('..');const out=path.join(root,'reports/phase3');
const real=JSON.parse(fs.readFileSync(path.join(out,'live-analysis.json'),'utf8'));
const fixture=JSON.parse(fs.readFileSync(path.join(out,'fixture-lesson.json'),'utf8'));
const oldBank=JSON.parse(fs.readFileSync(path.join(root,'reports/phase3-before-bank.json'),'utf8'));
const access=fs.readFileSync(path.join(root,'backend/data/teacher-access.txt'),'utf8').trim();
async function login(p:Page){await p.goto('/');await p.getByLabel('Mã truy cập giáo viên').fill(access);await p.getByRole('button',{name:'Vào không gian giáo viên'}).click();await expect(p.getByRole('heading',{name:/Hôm nay/})).toBeVisible();await expect(p.locator('.busy-banner')).toHaveCount(0);}
async function open(p:Page,title:string){await p.getByRole('button',{name:'Thư viện bài học',exact:false}).click();await p.locator('.lesson-card').filter({hasText:title}).first().click();await expect(p.getByRole('heading',{name:'Không gian kiểm duyệt'})).toBeVisible();}
async function approve(p:Page){
 let changed=false;
 for(const card of await p.locator('.question-editor').all()){
  if(!await card.getByLabel('Tạm ẩn câu này khỏi học sinh').isChecked()){
   const box=card.locator('.approval-check input');if(!await box.isChecked()){await box.check();changed=true;}
  }
 }
 await expect(p.locator('.busy-banner')).toHaveCount(0);
 const saveButton=p.getByRole('button',{name:/Lưu thay đổi/});
 if(changed||await saveButton.isEnabled()){
  await expect(saveButton).toBeEnabled();await saveButton.click();await expect(saveButton).toBeDisabled();await expect(p.locator('.busy-banner')).toHaveCount(0);
 }
 const publish=p.getByRole('button',{name:'Xuất bản',exact:true});await publish.click();await expect(p.locator('.busy-banner')).toHaveCount(0);
 if(!await p.locator('.share-panel').isVisible() && (await p.locator('.alert.success').allTextContents()).join(' ').includes('bấm xuất bản lần nữa')){await publish.click();}
 await expect(p.locator('.share-panel')).toBeVisible();
}
async function pixels(p:Page,expectedId:string){const img=p.locator('.student-question-media img');await expect(img).toBeVisible();await expect(img).toHaveAttribute('src','/api/media/'+expectedId);await expect.poll(()=>img.evaluate(el=>(el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);expect(await img.evaluate(el=>getComputedStyle(el).objectFit)).toBe('contain');expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);}

test('real input PPTX renders: teacher preview then publish a verified crop without caption answer',async({page})=>{
 await login(page);await page.request.post('/api/lessons/'+real.lesson_id+'/unpublish');await page.reload();await open(page,'QA · Our school facilities');
 const card=page.locator('.question-editor').first();await expect(card.locator('.teacher-media-preview img')).toHaveAttribute('src','/api/media/'+real.cropped_asset_id);
 await card.getByRole('combobox',{name:'Loại dữ kiện',exact:true}).selectOption('visual');await card.getByRole('textbox',{name:'Đoạn nguồn làm dữ kiện (hiển thị cho câu đọc hiểu)',exact:true}).fill('');await page.getByRole('button',{name:/Lưu thay đổi/}).click();await expect(page.locator('.alert.success')).toContainText('Đã lưu');await approve(page);await page.screenshot({path:path.join(out,'after-real-pptx-teacher.png'),fullPage:true});
 await page.getByRole('link',{name:'Mở bài học'}).click();await page.getByRole('button',{name:/Quiz Challenge/}).click();
 await pixels(page,real.cropped_asset_id);await page.screenshot({path:path.join(out,'after-real-pptx-student.png'),fullPage:true});
 await page.locator('.answer-options').getByRole('button').filter({hasText:'Three'}).click();await expect(page.locator('.feedback')).toContainText('Great job!');await page.locator('.feedback button').click();await expect(page.locator('.result-medal')).toContainText('100');
});

test('teacher sees missing-data warning, cannot publish wrong image, can replace with correct source picture',async({page})=>{
 await login(page);await page.request.post('/api/lessons/'+fixture.lesson_id+'/unpublish');await page.reload();await open(page,'QA · Hình học liệu');
 const bag=page.locator('.question-editor').nth(1);
 await bag.getByRole('combobox',{name:'Ảnh học liệu của câu hỏi',exact:true}).selectOption(fixture.assets[1]);
 await page.getByRole('button',{name:/Lưu thay đổi/}).click();await expect(bag.locator('.evidence-editor .alert')).toContainText('vật thể');
 await page.getByRole('button',{name:'Xuất bản',exact:true}).click();await expect(page.locator('.alert.error')).toContainText('duyệt');
 await page.screenshot({path:path.join(out,'teacher-wrong-image-blocked.png'),fullPage:true});
 await bag.getByRole('combobox',{name:'Ảnh học liệu của câu hỏi',exact:true}).selectOption(fixture.assets[0]);
 await page.getByRole('button',{name:/Lưu thay đổi/}).click();await expect(bag.locator('.evidence-editor .alert')).toHaveCount(0);
 await approve(page);
 const saved=await (await page.request.get('/api/lessons/'+fixture.lesson_id)).json();expect(saved.questions.every((q:any)=>q.approved&&q.validation_status==='valid')).toBe(true);
});

for(const [label,width,height] of [['desktop',1280,900],['tablet',768,1024],['mobile',390,844]] as const){
 test('bag color, apple count, spatial relation show actual matching pictures on '+label,async({page})=>{
  await page.setViewportSize({width,height});await page.goto('/?visual='+label+'#/play/'+fixture.code);await page.getByRole('button',{name:/Quiz Challenge/}).click();
  const cases=[['school-bag','What color is the school bag?','blue',fixture.assets[0]],['apples','How many apples are there?','Three',fixture.assets[1]],['position','Where is the ball?','Under the table',fixture.assets[2]]];
  for(const [name,prompt,answer,id] of cases){await expect(page.locator('.play-question')).toHaveText(prompt);await pixels(page,id);const button=page.locator('.answer-options button').filter({hasText:answer});await expect(button).toBeEnabled();await page.screenshot({path:path.join(out,`after-${name}-${label}.png`),fullPage:true});await button.click();await expect(page.locator('.feedback')).toContainText('Great job!');await page.locator('.feedback button').click();}
  await expect(page.locator('.result-medal')).toContainText('100');
 });
}

for(const [kind,label,count] of [['vocabulary','Learn Vocabulary',1],['quiz','Quiz Challenge',3],['match','Match the Words',2],['listen','Listen & Choose',1],['fill','Fill in the Blanks',1]] as const){
 test(`broken image prevents guessing and skips without penalty in ${kind}`,async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.route('**/api/media/**',r=>r.abort());await page.goto('/?broken='+kind+'#/play/'+fixture.code);await page.getByRole('button',{name:new RegExp(label.replace('&','&'))}).click();
  for(let i=0;i<count;i++){
   await expect(page.locator('.media-unavailable')).toContainText('Ảnh không tải được');await expect(page.locator('.play-answers')).toHaveAttribute('disabled','');for(const control of await page.locator('.play-answers button,.play-answers input').all())await expect(control).toBeDisabled();
   if(kind==='quiz'&&i===0)await page.screenshot({path:path.join(out,'image-error-no-guess-mobile.png'),fullPage:true});
   await page.getByRole('button',{name:'Bỏ qua không trừ điểm',exact:true}).click();await expect(page.locator('.feedback')).toContainText('không trừ điểm');await page.locator('.feedback button').click();
  }
  await expect(page.locator('.result-medal')).toContainText('—');await expect(page.locator('.finish-screen')).toContainText('không tính vào điểm');
 });
}

test('recovered original VML worksheet: source reading is yellow/red, correct bag and book images are shown',async({page})=>{
 const repair=JSON.parse(fs.readFileSync(path.join(out,'original-docx-repair.json'),'utf8'));expect(repair.original_sha256_matches).toBe(true);
 await login(page);await page.request.post('/api/lessons/'+repair.lesson_id+'/unpublish');await page.reload();await open(page,'BÀi tập');await approve(page);
 await page.getByRole('link',{name:'Mở bài học'}).click();await page.getByRole('button',{name:/Quiz Challenge/}).click();
 await expect(page.locator('.reading-evidence')).toContainText('It is yellow');await pixels(page,repair.crops['school bag']);await expect(page.locator('.play-question')).toHaveText('What color is the school bag?');
 await page.screenshot({path:path.join(out,'after-original-bag-correct-source.png'),fullPage:true});await page.locator('.answer-options button').filter({hasText:'Yellow'}).click();await expect(page.locator('.feedback')).toContainText('Great job!');await page.locator('.feedback button').click();
 await page.getByRole('button',{name:/Về bản đồ hành trình/}).click();await page.getByRole('button',{name:/Listen & Choose/}).click();await pixels(page,repair.crops.book);
 await page.screenshot({path:path.join(out,'after-original-book-correct-source.png'),fullPage:true});await page.locator('.answer-options button').filter({hasText:'Red'}).click();await expect(page.locator('.feedback')).toContainText('Great job!');await page.locator('.feedback button').click();await expect(page.locator('.result-medal')).toContainText('100');
});

test('saved reading lesson needs no picture or AI; old false exercise answers stay hidden without rewriting history',async({page})=>{
 const original=oldBank.find((l:any)=>l.title==='BÀi tập');await login(page);
 const current=await (await page.request.get('/api/lessons/'+original.id)).json();const bag=current.questions.find((q:any)=>q.prompt==='What color is the school bag?');expect(bag.hidden).toBe(true);expect(bag.answer).toBe('blue');expect(bag.validation_status).toBe('blocked');
 await open(page,'BÀi tập');await expect(page.locator('.question-editor').nth(1).locator('.evidence-editor .alert')).toContainText('chưa có ảnh');
 await page.screenshot({path:path.join(out,'after-original-bag-hidden-teacher.png'),fullPage:true});
 await page.goto('/?hidden-bag=1#/play/'+original.code);await expect(page.getByRole('button',{name:/Quiz Challenge/})).toBeVisible();const safe=await (await page.request.post('/api/play/'+original.code+'/start',{data:{mode:'quiz'}})).json();expect(safe.questions.every((q:any)=>q.id!==bag.id)).toBe(true);await page.screenshot({path:path.join(out,'after-original-bag-hidden-student.png'),fullPage:true});
 const standard=oldBank.find((l:any)=>l.title==='Unit 6 Lesson 2 Period 3');
 await page.route('**/api/media/**',r=>r.abort());await page.goto('/?reading=1#/play/'+standard.code);await page.getByRole('button',{name:/Quiz Challenge/}).click();await expect(page.locator('.reading-evidence')).toContainText('town');await expect(page.locator('.student-question-media')).toHaveCount(0);await expect(page.locator('.answer-options button').first()).toBeEnabled();
 await page.screenshot({path:path.join(out,'reading-data-visible-without-image.png'),fullPage:true});
});

test('real Gemini visual output is reviewed and played with its real PPTX image',async({page})=>{
 const generated=JSON.parse(fs.readFileSync(path.join(out,'live-visual-generation.json'),'utf8'));expect(generated.status).toBe('PASS');
 await login(page);await page.request.post('/api/lessons/'+generated.lesson_id+'/unpublish');await page.reload();await open(page,'QA · AI nhìn ảnh từ PowerPoint');
 const q=page.locator('.question-editor').first();await expect(q.getByRole('combobox',{name:'Loại dữ kiện',exact:true})).toHaveValue('visual');
 await approve(page);await page.getByRole('link',{name:'Mở bài học'}).click();await page.getByRole('button',{name:/Quiz Challenge/}).click();
 await pixels(page,real.cropped_asset_id);await page.screenshot({path:path.join(out,'after-ai-generated-real-pptx.png'),fullPage:true});
 await page.locator('.answer-options button').filter({hasText:'Three'}).click();await expect(page.locator('.feedback')).toContainText('Great job!');await page.locator('.feedback button').click();await expect(page.locator('.result-medal')).toContainText('100');
});

test('all five visual activities complete successfully with cached/repeated source images',async({page})=>{
 await login(page);const lesson=await (await page.request.get('/api/lessons/'+fixture.lesson_id)).json();
 const questions=lesson.questions.filter((q:any)=>!q.hidden);expect(questions.length).toBe(8);
 await page.goto('/?all-visual=1#/play/'+fixture.code);await page.getByRole('button',{name:/Bắt đầu hành trình/}).click();
 for(const q of questions){
  await expect(page.locator('.play-question')).toHaveText(q.prompt);await pixels(page,q.image_asset_id);
  if(q.kind==='fill'){await page.getByLabel('Từ còn thiếu là…').fill(q.answer);await page.getByRole('button',{name:'Kiểm tra',exact:true}).click();}
  else if(q.kind==='match')await page.locator('.matching-board>div').nth(1).getByRole('button',{name:q.answer,exact:true}).click();
  else await page.locator('.answer-options button').filter({hasText:q.answer}).click();
  await expect(page.locator('.feedback')).toContainText('Great job!');await page.locator('.feedback button').click();
 }
 await expect(page.locator('.result-medal')).toContainText('100');await expect(page.locator('.finish-stats')).toContainText('8/8');
 await page.screenshot({path:path.join(out,'all-five-visual-activities-result.png'),fullPage:true});
});
