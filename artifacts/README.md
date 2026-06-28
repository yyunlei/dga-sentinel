# Model Artifacts

This directory contains trained ML model files that are **not included** in the repository due to size.

## Directory Structure

```
artifacts/
  binary/
    binary_classification_model.pkl   # XGBoost binary classifier (DGA vs benign)
    binary_dataset.csv                # Training dataset for binary model
    bigram_vectorizer.pkl             # char 2-gram TF-IDF vectorizer
    trigram_vectorizer.pkl            # char 3-gram TF-IDF vectorizer
    quadgram_vectorizer.pkl           # char 4-gram TF-IDF vectorizer
  multi/
    multiclass_classification_model.h5  # CNN-Attention multiclass model
    multi_dataset.csv                   # Training dataset for multiclass model
    encoder_multi.pkl                   # Label encoder
    tokenizer.pkl                       # Character tokenizer
```

## Binary Classifier — Feature Pipeline

The binary DGA detector uses **full character n-gram TF-IDF** features (not aggregated
statistics), which is the key to >99% accuracy. The feature vector (9698 dims) is:

```
lexical(22) | entropy(4) | bigram TF-IDF(3000) | trigram TF-IDF(5000) | quadgram TF-IDF(3000)
```

Training (`scripts/train_binary_xgb.py`) and inference
(`src/common/features/ngram.py :: NgramFeatureExtractor.build`) share the exact same
column order and vectorizers — a smoke test asserts the train/serve vectors are identical.
XGBoost is a tree model (scale-invariant), so **no StandardScaler** is used; features stay
sparse.

### Held-out performance (20%, deduped)

| Scope | Accuracy | ROC-AUC | Recall @ FPR=1% |
|-------|----------|---------|-----------------|
| Full task (incl. dictionary-style DGA) | 99.12% | 99.95% | 99.11% |
| Algorithmic DGA (SLD entropy ≥ 3.0)    | 99.50% | 99.99% | — |

Dictionary-style DGA (word-like, e.g. `ylitutopiz.top`) and unusual-but-legitimate domains
are the residual hard cases; full n-gram features capture the specific malicious character
patterns that aggregated statistics miss.

## Obtaining the Models

### Option 1: Train from scratch

```bash
# Binary classifier (full n-gram XGBoost, ~99.1% accuracy)
PYTHONPATH=src python scripts/train_binary_xgb.py

# Multiclass classifier
python artifacts/multi/multy.py
```

`scripts/train_binary_xgb.py` reads `artifacts/binary/binary_dataset.csv`, deduplicates,
fits the TF-IDF vectorizers, trains XGBoost with early stopping, prints held-out metrics,
and saves the vectorizers + model back into `artifacts/binary/`.

> `scripts/train_binary_cnn.py` is a **research** char-CNN baseline (runs inside the Docker
> scoring container, which ships TensorFlow). It confirmed that a CNN converges to the same
> ~98.5% ceiling as feature-based XGBoost on the full dataset — kept for reference, not used
> in production.

Training data can be sourced from `DGA-DataSet/` (see `DGA-DataSet/README.md`).

### Option 2: Git LFS (future)

If this repository adds Git LFS support, run:

```bash
git lfs pull
```

## Notes

- `.pkl` files require scikit-learn and XGBoost compatible with the versions in `requirements.txt`
- `.h5` files require TensorFlow/Keras; load with `tf.keras.models.load_model()`
- The scoring service will fail to start if model files are missing; it logs a clear error indicating which file is absent
