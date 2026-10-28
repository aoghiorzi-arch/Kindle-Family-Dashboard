"""Offline 600x800 display renderer; no external calls, Kindle access or credentials."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from datetime import datetime
import hashlib, io, os, tempfile, textwrap

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
  while draw.textbbox((0,0),word,font=font(21,'italic'))[2] > width:
   if cur: lines.append(cur); cur=''
   lo,hi=1,len(word)
   while lo<hi:
    mid=(lo+hi+1)//2
    if draw.textbbox((0,0),word[:mid],font=font(21,'italic'))[2]<=width: lo=mid
    else: hi=mid-1
   lines.append(word[:lo]); word=word[lo:]
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
 date_text,date_font=fit(d,f"{dt.day} {dt.strftime('%B')}",295,53,'serif',34)
 d.text((left,112),date_text,font=date_font,fill=BLACK,anchor='lt')
 txt(left,183,dt.strftime('%Y'),18,'sans',GRAY)
 weather=data.get('weather',{})
 temperature=weather.get('temperature')
 temp=str(temperature)+'°' if temperature is not None else '—'
 temp,tfont=fit(d,temp,185,50,'serif',32)
 tw=d.textbbox((0,0),temp,font=tfont)[2]
 d.text((right-tw,112),temp,font=tfont,fill=BLACK,anchor='lt')
 cond,cf=fit(d,weather.get('condition','Weather unavailable'),220,17,'sans')
 bbox=d.textbbox((0,0),cond,font=cf);d.text((right-(bbox[2]-bbox[0]),180),cond,font=cf,fill=GRAY,anchor='lt')
 age=weather.get('age_minutes')
 if age is not None and age>=STALE_MINUTES: # visible hint that the forecast is old
  stale=f'Updated {age//60} h ago' if age<48*60 else f'Updated {age//1440} days ago'
  txt_right(206,stale,15,'sans',GRAY)
 rule(226)
 txt(left,245,'COMING UP',18,'bold',GRAY)
 all_events=list(data.get('events',[]))
 events=all_events[:3]
 if not events: txt(left,293,'No events scheduled',23,'italic',GRAY)
 for i,event in enumerate(events):
  y=292+i*52
  title='Busy' if event.get('private') else event.get('title','Untitled')
  title,tf=fit(d,title,375,25,'sans',19)
  d.text((left,y),title,font=tf,fill=BLACK)
  et=str(event.get('time',''))
  ew=d.textbbox((0,0),et,font=font(22,'sans'))[2]
  d.text((right-ew,y+2),et,font=font(22,'sans'),fill=GRAY)
 if len(all_events)>3:
  remaining=len(all_events)-3
  txt(left,451,f'+{remaining} more event'+('' if remaining==1 else 's'),16,'sans',GRAY)
 rule(478)
 txt(left,500,'OUTDOORS',18,'bold',GRAY)
 sunset,sunset_font=fit(d,'Sunset  '+str(weather.get('sunset','—')),285,24,'sans',20)
 d.text((left,538),sunset,font=sunset_font,fill=BLACK,anchor='lt')
 txt(365,500,'SHOPPING',18,'bold',GRAY)
 count=sum(not x.get('done',False) for x in data.get('shopping',[]))
 shopping,shopping_font=fit(d,f'{count} item'+('' if count==1 else 's')+' to get',191,23,'sans',18)
 d.text((365,538),shopping,font=shopping_font,fill=BLACK,anchor='lt')
 rule(598)
 txt(left,622,'A THOUGHT FOR TODAY',18,'bold',GRAY)
 quote=data.get('quote',{})
 thought=str(quote.get('text','')).strip('“”').strip()
 q='“'+thought+'”' if thought else ''
 lines,truncated=quote_lines(d,q)
 if truncated: lines[-1]=fit(d,lines[-1].rstrip('”')+'…',490,21,'italic',21)[0]
 for i,line in enumerate(lines): txt(left,665+i*29,line,21,'italic')
 if not lines: txt(left,665,'No thought selected',21,'italic',GRAY)
 source, sf=fit(d,quote.get('attribution',''),490,18,'sans',15)
 d.text((left,729),source,font=sf,fill=GRAY,anchor='lt')
 rule(765)
 txt(left,776,'TODAY  •  PREVIEW',15,'bold',GRAY)
 txt_right(776,'600 × 800',15,'sans',GRAY)
 return im

def png_bytes(data):
 image=render(data); b=io.BytesIO();image.save(b,format='PNG',optimize=True,dpi=(DPI,DPI));return b.getvalue()

def atomic_write(path, body):
 """Publish complete frames only; a failed write leaves the previous frame intact."""
 p = Path(path)
 p.parent.mkdir(parents=True, exist_ok=True)
 name = None
 try:
  with tempfile.NamedTemporaryFile(dir=p.parent, prefix='.frame-', delete=False) as f:
   name = f.name
   f.write(body)
   f.flush()
   os.fsync(f.fileno())
  os.replace(name, p)
 finally:
  if name and os.path.exists(name): os.unlink(name)

def save_frame(data,path):
 b=png_bytes(data); p=Path(path);atomic_write(p,b)
 return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}

