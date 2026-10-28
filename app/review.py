"""Generate fictional display scenarios and a printable physical-size review sheet.

Run python3 -m app.review; open data/display-review/index.html and print at 100%.
The HTML embeds each PNG, so a saved copy can be opened without the server.
"""
import base64
import copy
import html
import json
from pathlib import Path
from . import render


def scenarios():
 sample = json.loads((Path(__file__).parent/'seed.json').read_text())
 cases = [('Typical household day', sample)]
 long = copy.deepcopy(sample)
 long.update(date='2026-09-30')
 long['weather'].update(temperature=-18, condition='Heavy rain and blustery conditions throughout the afternoon', age_minutes=185)
 long['events'] = [
  {'title': 'School parents evening and arrangements for the forthcoming residential trip', 'time': '23:59'},
  {'title': 'Fictional private appointment', 'time': '09:00', 'private': True},
  {'title': 'A very long family activity title to test how event text fits', 'time': ''},
  {'title': 'Fourth event', 'time': '18:00'}]
 long['shopping'] = [{'title': 'Fictional item', 'done': False}] * 500
 long['quote'] = {'text': 'A single deliberately unbroken word: ' + 'W' * 250,
                  'attribution': 'A deliberately long fictional attribution ' * 8}
 cases.append(('Long text, stale weather, private event and overflow', long))
 sparse = {'date': '2026-12-31', 'weather': {}, 'shopping': [], 'events': [], 'quote': {}}
 cases.append(('Empty day and unavailable data', sparse))
 one = copy.deepcopy(sample)
 one['shopping'] = [{'title': 'One item', 'done': False}]
 one['events'] = [{'title': 'Fictional confidential appointment', 'private': True, 'time': '12:00'}]
 cases.append(('One shopping item and private appointment', one))
 return cases


def build(directory):
 directory = Path(directory)
 directory.mkdir(parents=True, exist_ok=True)
 width_mm, height_mm = render.W/render.DPI*25.4, render.H/render.DPI*25.4
 sections = []
 for index, (label, data) in enumerate(scenarios(), 1):
  body = render.png_bytes(data)
  render.atomic_write(directory/f'{index}.png', body)
  encoded = base64.b64encode(body).decode('ascii')
  sections.append(f'<section><h2>{html.escape(label)}</h2><p>Print at 100% / actual size. Disable fit-to-page and headers/footers.</p>'
   f'<img src="data:image/png;base64,{encoded}" alt="{html.escape(label)}">'
   '<p class="measure">This line must measure 50 mm</p>'
   '<p>Check at your intended viewing distance: date, event text, time, weather, private-event masking, ellipses and verse.</p>'
   '<p>Review: □ readable □ no clipping □ private titles hidden<br>Viewing distance: ______  Notes: ______________________</p></section>')
 page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Family Board physical-size review</title>
<style>@page{{size:A4;margin:15mm}}body{{font:12pt system-ui;color:#222;background:white;margin:0}}
section{{break-after:page;max-width:180mm;margin:12mm auto}}section:last-child{{break-after:auto}}
h2{{font-size:16pt}}p{{max-width:165mm;line-height:1.4}}img{{display:block;width:{width_mm:.6f}mm;height:{height_mm:.6f}mm;border:0}}
.measure{{width:50mm;border-top:1px solid black;padding-top:3mm;font-size:9pt}}
@media print{{section{{margin:0}}}}</style>
<body>{''.join(sections)}</body></html>'''
 (directory/'index.html').write_text(page)
 return directory/'index.html'


if __name__ == '__main__':
 print(build(Path(__file__).resolve().parents[1]/'data'/'display-review'))
