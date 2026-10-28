import unittest
from PIL import Image, ImageDraw
from app import content
from app.render import quote_lines

class ContentTest(unittest.TestCase):
 def test_same_day_same_verse(self):
  self.assertEqual(content.verse_for('2026-10-28'), content.verse_for('2026-10-28'))

 def test_days_rotate_through_verses(self):
  seen = {content.verse_for(f'2026-10-{d:02d}')['attribution'] for d in range(1, 29)}
  self.assertGreater(len(seen), 5)

 def test_every_verse_fits_two_lines_without_truncation(self):
  draw = ImageDraw.Draw(Image.new('RGB', (600, 800)))
  for verse in content.VERSES:
   lines, truncated = quote_lines(draw, '“' + verse['text'] + '”')
   self.assertFalse(truncated, verse['attribution'])

 def test_bad_date_is_rejected(self):
  with self.assertRaises(ValueError):
   content.verse_for('28/10/2026')

if __name__ == '__main__':
 unittest.main()
