#!/usr/bin/env python3
"""Render a validated pre-production master into PDF, EPUB, cover, and manifest."""
from __future__ import annotations
import argparse, html, json, re, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

ROOT=Path(__file__).resolve().parents[1]
LABEL='PRE-PRODUCTION — NOT YET DAILY PRODUCTION'

def target(date:str)->Path:
 y,m,_=date.split('-'); return ROOT/'editions'/y/m/date

def fonts(size, bold=False):
 candidates=['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
 for p in candidates:
  if Path(p).exists(): return ImageFont.truetype(p,size)
 return ImageFont.load_default()

def cover(path:Path,date:str):
 im=Image.new('RGB',(1200,1600),'#f3ead8'); d=ImageDraw.Draw(im)
 d.rectangle((0,0,1200,190),fill='#142c2b'); d.text((72,45),'DRAGON',font=fonts(86,True),fill='#f4c15d')
 d.text((75,215),'DAILY NEWSPAPER',font=fonts(48,True),fill='#142c2b')
 # Editorial illustration: abstract water lines, open book, and rising sun; no documentary claim.
 d.ellipse((400,380,800,780),fill='#e88b55');
 for y in range(650,1120,70): d.arc((100,y-80,1100,y+100),180,360,fill='#267b82',width=18)
 d.polygon([(170,920),(580,850),(580,1250),(170,1320)],fill='#fffaf0',outline='#142c2b')
 d.polygon([(1030,920),(620,850),(620,1250),(1030,1320)],fill='#fffaf0',outline='#142c2b')
 d.line((600,850,600,1250),fill='#142c2b',width=12)
 d.rectangle((0,1400,1200,1600),fill='#142c2b')
 d.text((62,1425),'PRE-PRODUCTION',font=fonts(47,True),fill='#f4c15d')
 d.text((62,1490),'NOT YET DAILY PRODUCTION',font=fonts(34,True),fill='white')
 d.text((820,1500),date,font=fonts(27),fill='white')
 im.save(path,'WEBP',quality=92,method=6)

def pdf(path:Path,md:str,date:str):
 # Use a Unicode TrueType font: the master contains Darija Latin punctuation
 # such as em dashes that the built-in Helvetica encoding cannot represent
 # reliably in every PDF consumer.
 regular_candidates=['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','C:/Windows/Fonts/arial.ttf','C:/Windows/Fonts/segoeui.ttf']
 bold_candidates=['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf','C:/Windows/Fonts/arialbd.ttf','C:/Windows/Fonts/segoeuib.ttf']
 regular=next((p for p in regular_candidates if Path(p).exists()), '')
 bold=next((p for p in bold_candidates if Path(p).exists()), '')
 if regular and bold:
  pdfmetrics.registerFont(TTFont('DragonDejaVu',regular))
  pdfmetrics.registerFont(TTFont('DragonDejaVu-Bold',bold))
  regular_font='DragonDejaVu'; bold_font='DragonDejaVu-Bold'
 else:
  regular_font='Helvetica'; bold_font='Helvetica-Bold'
 styles=getSampleStyleSheet(); body=ParagraphStyle('body',parent=styles['BodyText'],fontName='Helvetica',fontSize=9.2,leading=13,spaceAfter=4,textColor=HexColor('#172b2a'))
 body.fontName=regular_font
 h1=ParagraphStyle('h1',parent=styles['Heading1'],fontName=bold_font,fontSize=21,leading=25,textColor=HexColor('#142c2b'))
 h2=ParagraphStyle('h2',parent=styles['Heading2'],fontName=bold_font,fontSize=15,leading=19,spaceBefore=10,textColor=HexColor('#9b442e'))
 def footer(c,doc):
  c.saveState(); c.setFont(regular_font,7); c.setFillColor(HexColor('#555555')); c.drawString(18*mm,10*mm,f'DRAGON - {LABEL.replace("—", " - ")} - {date}'); c.drawRightString(192*mm,10*mm,str(doc.page)); c.restoreState()
 story=[]
 for line in md.splitlines():
  line=line.strip().replace('—',' - ')
  if not line: story.append(Spacer(1,3)); continue
  if line.startswith('# '): story.append(Paragraph(html.escape(line[2:]),h1)); continue
  if line.startswith('## '): story.append(Paragraph(html.escape(line[3:]),h2)); continue
  if line.startswith('- '): line='• '+line[2:]
  safe=html.escape(line).replace('**','')
  story.append(Paragraph(safe,body))
 doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=17*mm,bottomMargin=17*mm,title=f'DRAGON {date}',author='DRAGON Editorial Desk',subject=LABEL)
 doc.build(story,onFirstPage=footer,onLaterPages=footer)

def epub(path:Path,md:str,date:str,cover_bytes:bytes):
 sections=[]; current=[]; title='Edition'
 for line in md.splitlines():
  if line.startswith('## '):
   if current: sections.append((title,current))
   title=line[3:].strip(); current=[]
  else: current.append(line)
 if current: sections.append((title,current))
 def slug(i): return f'section-{i:02d}.xhtml'
 def render(lines):
  out=[]
  for x in lines:
   x=x.strip()
   if not x: continue
   if x.startswith('# '): out.append(f'<h1>{html.escape(x[2:])}</h1>')
   elif x.startswith('- '): out.append(f'<p>• {html.escape(x[2:])}</p>')
   else: out.append(f'<p>{html.escape(x).replace("**","")}</p>')
  return ''.join(out)
 nav=''.join(f'<li><a href="{slug(i)}">{html.escape(t)}</a></li>' for i,(t,_) in enumerate(sections,1))
 items=''.join(f'<item id="s{i}" href="{slug(i)}" media-type="application/xhtml+xml"/>' for i in range(1,len(sections)+1))
 spine=''.join(f'<itemref idref="s{i}"/>' for i in range(1,len(sections)+1))
 with zipfile.ZipFile(path,'w') as z:
  z.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
  z.writestr('META-INF/container.xml','<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
  z.writestr('OEBPS/content.opf',f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">dragon-{date}-preproduction</dc:identifier><dc:title>DRAGON Daily Newspaper — {date}</dc:title><dc:language>darija-Latn</dc:language><dc:creator>DRAGON Editorial Desk</dc:creator><dc:date>{date}</dc:date><dc:description>{LABEL}</dc:description></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="cover" href="cover.webp" media-type="image/webp" properties="cover-image"/>{items}</manifest><spine>{spine}</spine></package>''')
  z.writestr('OEBPS/nav.xhtml',f'''<!doctype html><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Table of Contents</title></head><body><nav epub:type="toc"><h1>Table of Contents</h1><ol>{nav}</ol></nav></body></html>''')
  z.writestr('OEBPS/cover.webp',cover_bytes)
  for i,(t,lines) in enumerate(sections,1): z.writestr('OEBPS/'+slug(i),f'''<!doctype html><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{html.escape(t)}</title></head><body><h1>{html.escape(t)}</h1>{render(lines)}</body></html>''')

def main():
 a=argparse.ArgumentParser(); a.add_argument('--date',required=True); x=a.parse_args(); p=target(x.date); md=(p/'edition.md').read_text(); sources=json.loads((p/'sources.json').read_text())
 cover(p/'cover.webp',x.date); pdf(p/'edition.pdf',md,x.date); epub(p/'edition.epub',md,x.date,(p/'cover.webp').read_bytes())
 sections=[line[3:].strip() for line in md.splitlines() if line.startswith('## ')]
 citations=len(re.findall(r'\[S\d+\]',md))
 manifest={'date':x.date,'mode':'preproduction','status':'published','language':'darija-latin','pdf':'edition.pdf','epub':'edition.epub','cover':'cover.webp','fact_check':'passed','language_check':'passed','sources_count':len(sources),'citations_count':citations,'sections':sections,'smoke_test':False,'label':LABEL}
 (p/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n', encoding='utf-8')
 print(f'rendered {p.relative_to(ROOT)}: {len(sources)} sources, {citations} citations, {len(sections)} sections')
if __name__=='__main__': main()
