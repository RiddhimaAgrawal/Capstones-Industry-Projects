"""Measure the sentiment engine's accuracy on a labelled CSV.

IMDB (Stanford) -> Kaggle 'IMDB Dataset of 50K Movie Reviews' CSV has columns: review,sentiment
Sentiment140   -> columns: target(0/4),...,text  (use --text-col text --label-col target)

  python scripts/eval_sentiment.py imdb.csv --text-col review --label-col sentiment --limit 5000
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analysis import sentiment  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("csv")
p.add_argument("--text-col", default="review")
p.add_argument("--label-col", default="sentiment")
p.add_argument("--limit", type=int, default=5000)
a = p.parse_args()

POS = {"positive", "pos", "1", "4"}
tp = tn = fp = fn = neutral = 0
with open(a.csv, newline="", encoding="latin-1") as f:
    for i, row in enumerate(csv.DictReader(f)):
        if i >= a.limit:
            break
        truth = row[a.label_col].strip().lower() in POS
        pred = sentiment(row[a.text_col])["label"]
        if pred == "neutral":
            neutral += 1
            pred = "positive"  # forced guess so accuracy is comparable with binary labels
        pred_pos = pred == "positive"
        tp += truth and pred_pos
        tn += (not truth) and (not pred_pos)
        fp += (not truth) and pred_pos
        fn += truth and (not pred_pos)

n = tp + tn + fp + fn
print(f"samples={n} accuracy={(tp + tn) / n:.3f} precision={tp / max(1, tp + fp):.3f} "
      f"recall={tp / max(1, tp + fn):.3f} neutral_forced={neutral}")
