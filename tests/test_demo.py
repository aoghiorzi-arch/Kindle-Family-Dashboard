import unittest, json, hashlib, io
from pathlib import Path
from app.render import png_bytes,render
from PIL import Image
DATA=json.loads((Path(__file__).parents[1]/'app'/'seed.json').read_text())
class TestDisplay(unittest.TestCase):
 def test_dimensions(self):
  img=Image.open(io.BytesIO(png_bytes(DATA)));self.assertEqual(img.size,(600,800))
 def test_determinism(self):self.assertEqual(png_bytes(DATA),png_bytes(DATA))
 def test_changes_change_frame(self):
  other=json.loads(json.dumps(DATA));other['shopping'].extend([{'title':str(i),'done':False} for i in range(9)])
  self.assertNotEqual(hashlib.sha256(png_bytes(DATA)).digest(),hashlib.sha256(png_bytes(other)).digest())
 def test_bundled_fonts_and_print_density(self):
  from app.render import FONT_DIR,FONTS
  self.assertTrue(all((FONT_DIR/name).exists() for name in FONTS.values()))
  img=Image.open(io.BytesIO(png_bytes(DATA)));self.assertAlmostEqual(img.info['dpi'][0],167,delta=0.01)
 def test_private_event_masked(self):
  # Privacy contract is that original event title is replaced by "Busy" before drawing.
  from unittest.mock import patch
  from PIL import ImageDraw
  original=ImageDraw.ImageDraw.text;drawn=[]
  def capture(self,xy,text,*args,**kwargs):drawn.append(str(text));return original(self,xy,text,*args,**kwargs)
  d=json.loads(json.dumps(DATA));d['events'][0]['private']=True
  with patch.object(ImageDraw.ImageDraw,'text',capture):render(d)
  self.assertIn('Busy',drawn);self.assertNotIn('School pickup',drawn)
if __name__=='__main__':unittest.main()
