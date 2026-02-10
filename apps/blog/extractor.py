import re
from collections import Counter

PERSIAN_STOPWORDS = set([
    'و', 'در', 'را', 'به', 'که', 'از', 'این', 'آن', 'با', 'برای', 'است', 'شد', 'تا', 'بر',
])


def extract_keywords(text: str, topn: int = 8):
    if not text:
        return []
    text = re.sub(r'<[^>]+>', ' ', text)
    words = re.findall(r'[\w\u0600-\u06FF]+', text)
    words = [w.strip().lower() for w in words if len(w.strip()) > 1]
    words = [w for w in words if w not in PERSIAN_STOPWORDS]
    cnt = Counter(words)
    return [w for w, _ in cnt.most_common(topn)]
