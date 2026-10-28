"""Offline 600x800 display renderer; no external calls, Kindle access or credentials."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from datetime import datetime
import hashlib, io, os, textwrap

W,H = 600,800
STALE_MINUTES = 60  # weather older than this shows its age on the display
DPI = 167  # Kindle Touch D01200 pixel density; lets a print at 100% show true physical size
BG='#FFFFFF'; BLACK='#161616'; GRAY='#575757'; LINE='#A0A0A0'
# Bundled OFL fonts (see app/fonts/OFL-Lato-NotoSerif.txt) keep renders reproducible across machines.
FONT_DIR=Path(__file__).resolve().parent/'fonts'
FONTS = {
 'sans': 'Lato-Regular.ttf', 'bold': 'Lato-Bold.ttf',
 'serif': 'NotoSerif-Variable.ttf', 'italic': 'NotoSerif-Italic-Variable.ttf'
}
def font(size, kind='sans'):
 return ImageFont.truetype(FONT_DIR/FONTS[kind], size)

def fit(draw,text,max_width,size=26,kind='sans',min_size=16):
 text=str(text or '')
 for s in range(size,min_size-1,-1):
  f=font(s,kind)
  if draw.textbbox((0,0),text,font=f)[2] <= max_width: return text,f
 ell='…'; f=font(min_size,kind)
 while text and draw.textbbox((0,0),text+ell,font=f)[2] > max_width: text=text[:-1]
 return text+ell,f

def quote_lines(draw,text,max_lines=2,width=490):
 """Wrap text to measured width. Returns (lines, truncated); the caller adds the ellipsis."""
 lines=[]; cur=''
 for word in text.split():
  trial=(cur+' '+word).strip()
  if draw.textbbox((0,0),trial,font=font(21,'italic'))[2] <= width: cur=trial
  else:
   if cur: lines.append(cur)
   cur=word
 if cur: lines.append(cur)
 return lines[:max_lines], len(lines)>max_lines

def render(data):
 im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im)
 left,right=44,556
 def txt(x,y,s,size=22,kind='sans',fill=BLACK): d.text((x,y),str(s),font=font(size,kind),fill=fill,anchor='lt')
 def txt_right(y,s,size,kind,fill=BLACK):
  f=font(size,kind); d.text((right-d.textbbox((0,0),str(s),font=f)[2],y),str(s),font=f,fill=fill,anchor='lt')
 def rule(y): d.line((left,y,right,y),fill=LINE,width=1)
 txt(left,29,'THE FAMILY BOARD',17,'bold',GRAY)
 txt_right(29,'TODAY',17,'bold',GRAY)
 rule(63)
 dt=datetime.fromisoformat(data['date'])
 txt(left,81,dt.strftime('%A').upper(),22,'bold',GRAY)
 txt(left,112,f"{dt.day} {dt.strftime('%B')}",53,'serif')
 txt(left,183,dt.strftime('%Y'),18,'sans',GRAY)
 weather=data.get('weather',{})
 temp=str(weather.get('temperature','—'))+'°'
 tfont=font(50,'serif'); tw=d.textbbox((0,0),temp,font=tfont)[2]
 d.text((right-tw,102),temp,font=tfont,fill=BLACK)
 cond,cf=fit(d,weather.get('condition','Weather unavailable'),220,17,'sans')
 bbox=d.textbbox((0,0),cond,font=cf);d.text((right-(bbox[2]-bbox[0]),171),cond,font=cf,fill=GRAY)
 age=weather.get('age_minutes')
 if age is not None and age>=STALE_MINUTES: # visible hint that the forecast is old
  stale=f'Updated {age//60} h ago' if age<48*60 else f'Updated {age//1440} days ago'
  txt_right(195,stale,15,'sans',GRAY)
 rule(226)
 txt(left,245,'COMING UP',18,'bold',GRAY)
 events=list(data.get('events',[]))[:3]
 if not events: txt(left,293,'No events scheduled',23,'italic',GRAY)
 for i,event in enumerate(events):
  y=292+i*52
  title='Busy' if event.get('private') else event.get('title','Untitled')
  title,tf=fit(d,title,375,25,'sans',19)
  d.text((left,y),title,font=tf,fill=BLACK)
  et=str(event.get('time',''))
  ew=d.textbbox((0,0),et,font=font(22,'sans'))[2]
  d.text((right-ew,y+2),et,font=font(22,'sans'),fill=GRAY)
 rule(478)
 txt(left,500,'OUTDOORS',18,'bold',GRAY)
 txt(left,538,'Sunset  '+str(weather.get('sunset','—')),24,'sans')
 txt(365,500,'SHOPPING',18,'bold',GRAY)
 count=sum(not x.get('done',False) for x in data.get('shopping',[]))
 txt(365,538,f'{count} items to get',23,'sans')
 rule(598)
 txt(left,622,'A THOUGHT FOR TODAY',18,'bold',GRAY)
 quote=data.get('quote',{})
 q='“'+str(quote.get('text','')).strip('“”')+'”'
 lines,truncated=quote_lines(d,q)
 if truncated: lines[-1]=lines[-1].rstrip('”')+'…'
 for i,line in enumerate(lines): txt(left,665+i*29,line,21,'italic')
 if not lines: txt(left,665,'No thought selected',21,'italic',GRAY)
 source, sf=fit(d,quote.get('attribution',''),490,18,'sans',15)
 txt(left,729,source,18,'sans',GRAY)
 rule(765)
 txt(left,776,'TODAY  •  PREVIEW',15,'bold',GRAY)
 txt_right(776,'600 × 800',15,'sans',GRAY)
 return im

def png_bytes(data):
 image=render(data); b=io.BytesIO();image.save(b,format='PNG',optimize=True,dpi=(DPI,DPI));return b.getvalue()

def save_frame(data,path):
 b=png_bytes(data); p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
