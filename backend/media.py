"""Content-addressed pixels + exact occurrence provenance. No filename semantics."""
import hashlib
import io
import json
import os
import posixpath
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}


def digest_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):digest.update(chunk)
    return digest.hexdigest()


def store_image(raw, root, document_hash, source, origin, **metadata):
    with Image.open(io.BytesIO(raw)) as opened:
        if opened.width*opened.height>40_000_000:
            raise ValueError('Ảnh vượt quá 40 megapixel.')
        image=ImageOps.exif_transpose(opened).convert('RGBA')
        crop=metadata.get('picture_crop')
        if crop:
            l,t,r,b=crop
            if l+r>=1 or t+b>=1 or min(crop)<0:
                raise ValueError('Vùng cắt không hợp lệ.')
            image=image.crop((int(l*image.width),int(t*image.height),int((1-r)*image.width),int((1-b)*image.height)))
        if metadata.get('flip_h'):image=ImageOps.mirror(image)
        if metadata.get('flip_v'):image=ImageOps.flip(image)
        if metadata.get('rotation'):image=image.rotate(-metadata['rotation'],expand=True)
        image.thumbnail((1600,1600))
        output=io.BytesIO();image.save(output,format='PNG')
    pixel_hash=hashlib.sha256(output.getvalue()).hexdigest()
    ident=hashlib.sha256(json.dumps([document_hash,source,origin,pixel_hash,metadata],sort_keys=True).encode()).hexdigest()
    folder=root/'media';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(ident+'.png');path.write_bytes(output.getvalue())
    info={'id':ident,'url':'/api/media/'+ident,'source':source,'document_hash':document_hash,'origin':origin,
          'width':image.width,'height':image.height,'pixel_hash':pixel_hash,'role':'unclassified','description':'',
          'facts':[],'answer_leak':True,'reviewed':False,'verified_by':'','metadata':metadata}
    sidecar=folder/(ident+'.json')
    if sidecar.exists():
        previous=json.loads(sidecar.read_text(encoding='utf-8'))
        if previous.get('pixel_hash')==pixel_hash:info=previous
    sidecar.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    return info


def asset_info(root, ident):
    if len(ident)!=64 or any(c not in '0123456789abcdef' for c in ident):return None
    path=root/'media'/(ident+'.json')
    if not path.exists() or not (root/'media'/(ident+'.png')).exists():return None
    info=json.loads(path.read_text(encoding='utf-8'))
    if digest_file(root/'media'/(ident+'.png'))!=info['pixel_hash']:return None
    return info


def write_info(root, info):
    (root/'media'/(info['id']+'.json')).write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')


def rels(archive,name):
    if name not in archive.namelist():return {}
    return {r.attrib['Id']:r.attrib.get('Target','') for r in ET.fromstring(archive.read(name)) if r.attrib.get('TargetMode')!='External'}


def extract_media(path, document, root, render=True):
    sha=digest_file(path);document['sha256']=sha;document['assets']=[]
    (root/'sources').mkdir(parents=True,exist_ok=True)
    source_path=root/'sources'/(sha+path.suffix.lower())
    if not source_path.exists():
        import shutil
        shutil.copyfile(path,source_path)
    document['source_retained']=True
    assets=document['assets'];suffix=path.suffix.lower()
    if suffix=='.pptx':
        with ZipFile(path) as z:
            presentation=ET.fromstring(z.read('ppt/presentation.xml'))
            size=presentation.find('p:sldSz',NS); sw=int(size.attrib['cx']);sh=int(size.attrib['cy'])
            ids=rels(z,'ppt/_rels/presentation.xml.rels')
            for number,sid in enumerate(presentation.findall('p:sldIdLst/p:sldId',NS),1):
                target=ids[sid.attrib['{'+NS['r']+'}id']]
                name=target.lstrip('/') if target.startswith('/') else posixpath.normpath('ppt/'+target)
                slide=ET.fromstring(z.read(name));relationships=rels(z,posixpath.dirname(name)+'/_rels/'+posixpath.basename(name)+'.rels')
                grouped={id(p) for group in slide.findall('.//p:grpSp',NS) for p in group.findall('.//p:pic',NS)}
                for i,pic in enumerate(slide.findall('.//p:pic',NS)):
                    blip=pic.find('.//a:blip',NS)
                    if blip is None:continue
                    relative=relationships.get(blip.attrib.get('{'+NS['r']+'}embed',''))
                    if not relative:continue
                    part=relative.lstrip('/') if relative.startswith('/') else posixpath.normpath(posixpath.dirname(name)+'/'+relative)
                    crop=pic.find('.//a:srcRect',NS)
                    crop=[int(crop.attrib.get(k,0))/100000 for k in ['l','t','r','b']] if crop is not None else [0,0,0,0]
                    xfrm=pic.find('p:spPr/a:xfrm',NS);meta={'grouped':id(pic) in grouped,'picture_crop':crop,'part':part,'context':'isolated_picture'}
                    if xfrm is not None:
                        off=xfrm.find('a:off',NS);ext=xfrm.find('a:ext',NS)
                        if off is not None and ext is not None:meta['bbox']=[int(off.attrib['x'])/sw,int(off.attrib['y'])/sh,int(ext.attrib['cx'])/sw,int(ext.attrib['cy'])/sh]
                        meta.update(rotation=int(xfrm.attrib.get('rot',0))/60000,flip_h=xfrm.attrib.get('flipH')=='1',flip_v=xfrm.attrib.get('flipV')=='1')
                    try:assets.append(store_image(z.read(part),root,sha,number,f'picture-{i+1}',**meta))
                    except Exception:document['warnings'].append(f'Không chuyển được ảnh {i+1} slide {number}; dùng bản render nếu có.')
        if render and os.name!='nt':document['warnings'].append('Linux không có PowerPoint COM: chỉ trích ảnh gốc, không render toàn slide mới. Dùng PDF xuất từ PowerPoint nếu cần bố cục đầy đủ; ảnh nhóm/quan hệ vị trí phải được kiểm định.')
        if render:
            folder=root/'render-cache'/sha
            if os.name=='nt' and os.environ.get('ADVENTURE_RENDER_PPTX','1')!='0' and not all((folder/f'slide-{s["number"]}.png').exists() for s in document['sections']):
                try:
                    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/render_pptx.ps1'),'-Source',str(source_path.resolve()),'-Destination',str(folder.resolve())],capture_output=True,timeout=100,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception:document['warnings'].append('Không render được bằng PowerPoint. Ảnh nhóm/quan hệ vị trí cần giáo viên kiểm tra ngữ cảnh; không tự gán.')
            for s in document['sections']:
                png=folder/f'slide-{s["number"]}.png'
                if png.exists():assets.append(store_image(png.read_bytes(),root,sha,s['number'],'slide_render',context='full_slide',contains_source_text=True))
    elif suffix=='.pdf':
        import pymupdf
        with pymupdf.open(path) as pdf:
            for n,page in enumerate(pdf,1):
                assets.append(store_image(page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).tobytes('png'),root,sha,n,'page_render',context='full_page',contains_source_text=True))
                for i,block in enumerate(page.get_text('dict')['blocks']):
                    if block.get('type')==1 and block.get('image'):
                        try:assets.append(store_image(block['image'],root,sha,n,f'pdf-image-{i}',bbox=list(block['bbox']),context='isolated_picture'))
                        except Exception:document['warnings'].append(f'Không đọc được một ảnh trang {n}.')
    elif suffix=='.docx':
        with ZipFile(path) as z:
            xml=ET.fromstring(z.read('word/document.xml'));relationships=rels(z,'word/_rels/document.xml.rels')
            paragraphs=xml.findall('.//w:body/w:p',NS);offset=0;occurrence=0
            for p in paragraphs:
                text=''.join(t.text or '' for t in p.findall('.//w:t',NS))
                section=min(offset//3000+1,max(1,len(document['sections'])))
                for blip in p.findall('.//a:blip',NS):
                    relative=relationships.get(blip.attrib.get('{'+NS['r']+'}embed',''))
                    if not relative:continue
                    part=posixpath.normpath('word/'+relative);occurrence+=1
                    try:assets.append(store_image(z.read(part),root,sha,section,f'docx-image-{occurrence}',paragraph=text[:400],context='docx_paragraph',placement_uncertain=True))
                    except Exception:document['warnings'].append('Một ảnh DOCX chưa đọc được; không thể dùng làm dữ kiện.')
                for image in p.findall('.//{urn:schemas-microsoft-com:vml}imagedata'):
                    relative=relationships.get(image.attrib.get('{'+NS['r']+'}id',''))
                    if not relative:continue
                    part=posixpath.normpath('word/'+relative);occurrence+=1
                    try:assets.append(store_image(z.read(part),root,sha,section,f'docx-vml-{occurrence}',part=part,paragraph=text[:400],context='docx_vml',placement_uncertain=True))
                    except Exception:document['warnings'].append('Ảnh VML không chuyển được; câu phụ thuộc ảnh phải tạm chặn.')
                offset+=len(text)+1
            # Table/anchor/group pictures lacking reliable paragraph mapping: retain,
            # but flag uncertain and never auto-assign to a question.
            mapped={a['metadata'].get('part') for a in assets}
            if xml.findall('.//w:tbl//a:blip',NS):document['warnings'].append('Ảnh trong bảng/nhóm DOCX cần kiểm tra thủ công; không tự suy ra trang hoặc quan hệ.')
    # Keep reviewed derived regions when the same source is re-uploaded/audited.
    # Identity includes source hash, placement and pixels; never carry across files.
    for sidecar in (root/'media').glob('*.json'):
        saved=json.loads(sidecar.read_text(encoding='utf-8'))
        if saved.get('document_hash')==sha and saved.get('origin')=='teacher_crop' and saved.get('metadata',{}).get('parent_asset_id') in {a['id'] for a in assets}:
            verified=asset_info(root,saved['id'])
            if verified and not any(a['id']==saved['id'] for a in assets):assets.append(verified)
    for s in document['sections']:
        s['asset_ids']=[a['id'] for a in assets if a['source']==s['number']]
        if suffix in ('.pdf','.docx'):s['images']=sum(a['source']==s['number'] and not a['origin'].endswith('_render') for a in assets)
    return document
