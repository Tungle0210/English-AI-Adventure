"""Owned, deterministic regression artwork; NOT a replacement for a user's missing DOCX."""
from pathlib import Path
import json
import sys
from PIL import Image,ImageDraw
from pptx import Presentation
from pptx.util import Inches

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/phase3/fixtures';OUT.mkdir(parents=True,exist_ok=True)


def draw(name):
    im=Image.new('RGB',(720,480),'#fffdf5');d=ImageDraw.Draw(im)
    if name=='bag':
        d.arc((260,35,460,180),180,360,fill='#294e7d',width=25)
        d.rounded_rectangle((210,100,510,430),radius=55,fill='#357dcc',outline='#255489',width=9)
        d.rounded_rectangle((242,258,478,397),radius=25,fill='#2469b4',outline='#b5d9ef',width=5)
        d.line((255,285,467,285),fill='#e6c165',width=8);d.rectangle((443,279,453,309),fill='#f0ca6b')
        d.rounded_rectangle((258,142,462,228),radius=15,fill='#6ba6e2')
    elif name=='apples':
        for x in [150,360,570]:
            d.ellipse((x-76,175,x+76,355),fill='#df5549',outline='#ad3937',width=6)
            d.line((x,184,x+9,135),fill='#88633d',width=11)
            d.ellipse((x+8,133,x+65,165),fill='#7b9f50')
            d.arc((x-59,196,x+25,310),180,245,fill='#f6a296',width=10)
    else:
        d.rectangle((130,150,590,190),fill='#b8854f',outline='#795830',width=5)
        d.rectangle((150,190,179,420),fill='#c4935f');d.rectangle((541,190,570,420),fill='#c4935f')
        d.ellipse((290,285,425,420),fill='#efa44a',outline='#b87835',width=6)
        d.arc((298,291,418,414),20,170,fill='#fff5dc',width=7)
        d.line((130,425,590,425),fill='#d5d6be',width=4)
    path=OUT/(name+'.png');im.save(path);return path


def main():
    images={n:draw(n) for n in ['bag','apples','position']}
    prs=Presentation();prs.slide_width=Inches(12);prs.slide_height=Inches(7)
    s=prs.slides.add_slide(prs.slide_layouts[6])
    box=s.shapes.add_textbox(Inches(.3),Inches(.2),Inches(11),Inches(.5))
    box.text='Visual QA regression fixtures. Observe each individual picture.'
    for i,name in enumerate(images):s.shapes.add_picture(str(images[name]),Inches(.25+i*4),Inches(1.5),width=Inches(3.5))
    s2=prs.slides.add_slide(prs.slide_layouts[6]);s2.shapes.add_textbox(Inches(.2),Inches(.2),Inches(10),Inches(.5)).text='Grouped/cropped example; inspect context before use.'
    group=s2.shapes.add_group_shape();pic=group.shapes.add_picture(str(images['bag']),Inches(1),Inches(1),width=Inches(4));pic.crop_left=.1;pic.crop_right=.1
    prs.save(OUT/'visual-regression.pptx')
    # Also exercise actual DOCX embedded-image relationships and paragraph mapping.
    from docx import Document
    doc=Document();doc.add_paragraph('QA regression: school bag.');doc.add_picture(str(images['bag']),width=Inches(3));doc.save(OUT/'visual-regression.docx')
    from PIL import Image as PILImage
    PILImage.open(images['apples']).convert('RGB').save(OUT/'visual-regression.pdf','PDF')
    (OUT/'README.txt').write_text('Original deterministic QA artwork generated locally; no external assets. These fixtures test bag color, apple count and position. They are NOT the missing original DOCX and are never attached to its question automatically.\n',encoding='utf-8')
    print('QA_FIXTURES_CREATED')


if __name__=='__main__':main()
