import json
import os
import time
from typing import List, Dict
import numpy as np

from daemon.match.intent_classifier import SemanticContextClassifier

CORPUS_PATH = os.path.join(os.path.dirname(__file__), "data", "vocative_corpus.jsonl")

def run_benchmark():
    if not os.path.exists(CORPUS_PATH):
        raise FileNotFoundError(f"Corpus file not found: {CORPUS_PATH}. Run eval/generate_intent_corpus.py first.")

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f if line.strip()]

    classifier = SemanticContextClassifier()

    latencies_ms = []
    tp = 0  # True Positive: actual direct, predicted direct
    tn = 0  # True Negative: actual casual, predicted casual
    fp = 0  # False Positive: actual casual, predicted direct (False alarm!)
    fn = 0  # False Negative: actual direct, predicted casual (Missed call!)

    failures = []
    lang_stats: Dict[str, Dict[str, int]] = {}

    print(f"=== Benchmarking Morpho-Phonetic Vocative Engine on {len(samples)} Samples ===")

    for s in samples:
        text = s["text"]
        target = s["target"]
        expected_label = s["label"]
        lang = s.get("lang", "unknown")

        if lang not in lang_stats:
            lang_stats[lang] = {"total": 0, "correct": 0}
        lang_stats[lang]["total"] += 1

        t0 = time.perf_counter()
        res = classifier.classify(text, target)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(lat)

        pred_direct = res.is_direct_address
        actual_direct = (expected_label == "direct_address")

        if actual_direct and pred_direct:
            tp += 1
            lang_stats[lang]["correct"] += 1
        elif not actual_direct and not pred_direct:
            tn += 1
            lang_stats[lang]["correct"] += 1
        elif not actual_direct and pred_direct:
            fp += 1
            failures.append((s, res, "FALSE_POSITIVE (False Alarm)"))
        elif actual_direct and not pred_direct:
            fn += 1
            failures.append((s, res, "FALSE_NEGATIVE (Missed Direct Call)"))

    total = len(samples)
    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    print("\n----------------- Confusion Matrix -----------------")
    print(f"True Positives (Alerted correctly):        {tp:3d} / {tp+fn}")
    print(f"True Negatives (Suppressed correctly):     {tn:3d} / {tn+fp}")
    print(f"False Positives (Unwanted false alarms):   {fp:3d}")
    print(f"False Negatives (Missed user calls):       {fn:3d}")

    print("\n---------------- Classification Metrics ------------")
    print(f"Accuracy:   {accuracy * 100:.2f}%")
    print(f"Precision:  {precision * 100:.2f}%")
    print(f"Recall:     {recall * 100:.2f}%")
    print(f"F1 Score:   {f1 * 100:.2f}%")

    print("\n---------------- Per-Language Accuracy -------------")
    for lang, st in sorted(lang_stats.items()):
        acc = (st["correct"] / st["total"]) * 100 if st["total"] > 0 else 0.0
        print(f"Language [{lang:<4}]: {st['correct']:2d} / {st['total']:2d} ({acc:6.2f}%)")

    print("\n---------------- Latency Profile (CPU) -------------")
    print(f"Mean Latency:   {np.mean(latencies_ms):.4f} ms")
    print(f"Median (p50):   {np.median(latencies_ms):.4f} ms")
    print(f"95th percentile:{np.percentile(latencies_ms, 95):.4f} ms")
    print(f"99th percentile:{np.percentile(latencies_ms, 99):.4f} ms")

    if failures:
        print(f"\n[FAILURES] {len(failures)} mismatch(es) detected:")
        for s, res, reason in failures:
            safe_text = s['text'].encode('ascii', 'backslashreplace').decode('ascii')
            safe_target = s['target'].encode('ascii', 'backslashreplace').decode('ascii')
            print(f" - [{reason}] Id: {s['id']} | Target: {safe_target} | Text: \"{safe_text}\" -> Pred: {res.intent} (conf={res.confidence:.2f})")
    else:
        print("\nAll samples evaluated with ZERO classification errors!")

    assert fp == 0, f"Expected 0 false alarms, got {fp}"
    assert fn == 0, f"Expected 0 missed calls, got {fn}"

if __name__ == "__main__":
    run_benchmark()
