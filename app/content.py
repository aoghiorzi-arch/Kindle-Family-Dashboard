"""Daily thought for the display. Verses are from the King James Version (public domain).

Each date maps to the same verse every time, so a refresh never changes the day's frame.
No network calls. Check each verse against a printed Bible before it goes on a family display.
"""
import hashlib
from datetime import date

VERSES = [
 {'text': 'This is the day which the LORD hath made; we will rejoice and be glad in it.', 'attribution': 'Psalm 118:24 (KJV)'},
 {'text': 'They are new every morning: great is thy faithfulness.', 'attribution': 'Lamentations 3:23 (KJV)'},
 {'text': 'A merry heart doeth good like a medicine: but a broken spirit drieth the bones.', 'attribution': 'Proverbs 17:22 (KJV)'},
 {'text': 'Two are better than one; because they have a good reward for their labour.', 'attribution': 'Ecclesiastes 4:9 (KJV)'},
 {'text': 'And whatsoever ye do, do it heartily, as to the Lord, and not unto men;', 'attribution': 'Colossians 3:23 (KJV)'},
 {'text': 'God is our refuge and strength, a very present help in trouble.', 'attribution': 'Psalm 46:1 (KJV)'},
 {'text': 'In all thy ways acknowledge him, and he shall direct thy paths.', 'attribution': 'Proverbs 3:6 (KJV)'},
 {'text': 'Pleasant words are as an honeycomb, sweet to the soul, and health to the bones.', 'attribution': 'Proverbs 16:24 (KJV)'},
 {'text': 'To every thing there is a season, and a time to every purpose under the heaven:', 'attribution': 'Ecclesiastes 3:1 (KJV)'},
 {'text': 'Rejoice evermore. Pray without ceasing. In every thing give thanks.', 'attribution': '1 Thessalonians 5:16–18 (KJV, abridged)'},
]

def verse_for(day_iso):
 day = date.fromisoformat(day_iso).isoformat()
 digest = hashlib.sha256(day.encode()).digest()
 return dict(VERSES[int.from_bytes(digest[:4], 'big') % len(VERSES)])
