// Daily thought for the display. Verses are from the King James Version (public domain).
// Ported from app/content.py. The same date always gives the same verse, so a refresh never changes the day's frame.
// The text has not yet been checked against a printed Bible; do that before a family display relies on it.

export interface Thought {
  text: string;
  attribution: string;
}

export const VERSES: readonly Thought[] = [
  { text: "This is the day which the LORD hath made; we will rejoice and be glad in it.", attribution: "Psalm 118:24 (KJV)" },
  { text: "They are new every morning: great is thy faithfulness.", attribution: "Lamentations 3:23 (KJV)" },
  { text: "A merry heart doeth good like a medicine: but a broken spirit drieth the bones.", attribution: "Proverbs 17:22 (KJV)" },
  { text: "Two are better than one; because they have a good reward for their labour.", attribution: "Ecclesiastes 4:9 (KJV)" },
  { text: "And whatsoever ye do, do it heartily, as to the Lord, and not unto men;", attribution: "Colossians 3:23 (KJV)" },
  { text: "God is our refuge and strength, a very present help in trouble.", attribution: "Psalm 46:1 (KJV)" },
  { text: "In all thy ways acknowledge him, and he shall direct thy paths.", attribution: "Proverbs 3:6 (KJV)" },
  { text: "Pleasant words are as an honeycomb, sweet to the soul, and health to the bones.", attribution: "Proverbs 16:24 (KJV)" },
  { text: "To every thing there is a season, and a time to every purpose under the heaven:", attribution: "Ecclesiastes 3:1 (KJV)" },
  { text: "Rejoice evermore. Pray without ceasing. In every thing give thanks.", attribution: "1 Thessalonians 5:16–18 (KJV, abridged)" },
];

// First 32 bits of SHA-256 of the date, modulo the list length: the same index as the Python version.
export async function thoughtForDate(localDate: string): Promise<Thought> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(localDate));
  const bytes = new Uint8Array(digest);
  const first32 = ((bytes[0] << 24) >>> 0) + (bytes[1] << 16) + (bytes[2] << 8) + bytes[3];
  return VERSES[first32 % VERSES.length];
}
