# Model Artifacts

This directory contains trained ML model files that are **not included** in the repository due to size.

## Directory Structure

```
artifacts/
  binary/
    binary_classification_model.pkl   # XGBoost binary classifier (DGA vs benign)
    binary_dataset.csv                # Training dataset for binary model
    bigram_vectorizer.pkl             # N-gram feature vectorizer
    trigram_vectorizer.pkl
    unigram_vectorizer.pkl
    scaler.pkl                        # Feature scaler
  multi/
    multiclass_classification_model.h5  # CNN-Attention multiclass model
    multi_dataset.csv                   # Training dataset for multiclass model
    encoder_multi.pkl                   # Label encoder
    tokenizer.pkl                       # Character tokenizer
  test_dataset.csv                      # Evaluation dataset
```

## Obtaining the Models

### Option 1: Train from scratch

Use the training scripts in each subdirectory:

```bash
# Binary classifier
python artifacts/binary/binary.py

# Multiclass classifier
python artifacts/multi/multy.py
```

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
