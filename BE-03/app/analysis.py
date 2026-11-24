"""The sample 'product': a small text-analysis engine (sentiment, stats, keywords).

Sentiment is a lexicon + negation + intensifier model. It is deliberately simple
and dependency-free so the focus of the project stays on the API platform.
scripts/eval_sentiment.py measures its accuracy on the IMDB / Sentiment140 data."""
import re
from collections import Counter

POSITIVE = set("""good great excellent amazing awesome wonderful fantastic love loved lovely best better brilliant
enjoy enjoyed enjoyable fun funny happy beautiful perfect superb outstanding masterpiece favorite recommend
recommended impressive delightful charming entertaining touching moving gripping stunning nice pleasant
positive glad thrilled satisfying solid clever fresh heartwarming terrific incredible magnificent""".split())
NEGATIVE = set("""bad terrible awful horrible worst worse boring dull hate hated poor waste disappointing disappointed
disappointment mess stupid ugly annoying painful weak lame mediocre forgettable pathetic dreadful
unwatchable tedious sad angry negative fail failed failure broken useless nasty rubbish ridiculous
confusing overrated predictable shallow cringe""".split())
NEGATORS = {"not", "no", "never", "n't", "hardly", "without", "isn't", "wasn't", "don't", "didn't", "doesn't", "can't", "won't"}
INTENSIFIERS = {"very": 1.5, "really": 1.5, "extremely": 2.0, "absolutely": 2.0, "so": 1.3, "totally": 1.5, "highly": 1.5}
STOPWORDS = set("""a an the and or but if then of to in on at for with by from as is are was were be been being it its this that
these those i you he she we they them his her our your their my me do does did have has had not no so very just than
too can will would should could about into over after before also more most some any all""".split())

_WORD = re.compile(r"[A-Za-z']+")


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def sentiment(text: str) -> dict:
    tokens = tokenize(text)
    score = 0.0
    hits = 0
    for i, tok in enumerate(tokens):
        base = 1.0 if tok in POSITIVE else -1.0 if tok in NEGATIVE else 0.0
        if base == 0.0:
            continue
        weight = 1.0
        window = tokens[max(0, i - 3):i]
        if any(w in NEGATORS or w.endswith("n't") for w in window):
            base = -base * 0.8
        for w in window:
            weight = max(weight, INTENSIFIERS.get(w, 1.0))
        score += base * weight
        hits += 1
    normalized = score / (hits + 1.0) if hits else 0.0     # in (-1, 1)
    label = "positive" if normalized > 0.15 else "negative" if normalized < -0.15 else "neutral"
    return {"label": label, "score": round(normalized, 4), "matched_terms": hits, "tokens": len(tokens)}


def stats(text: str) -> dict:
    tokens = tokenize(text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    avg = sum(len(t) for t in tokens) / len(tokens) if tokens else 0.0
    return {
        "characters": len(text),
        "words": len(tokens),
        "unique_words": len(set(tokens)),
        "sentences": len(sentences),
        "avg_word_length": round(avg, 2),
        "reading_time_seconds": round(len(tokens) / 230 * 60, 1),  # ~230 wpm
    }


def keywords(text: str, top_n: int = 5) -> list[dict]:
    counts = Counter(t for t in tokenize(text) if t not in STOPWORDS and len(t) > 2)
    return [{"word": w, "count": c} for w, c in counts.most_common(top_n)]
