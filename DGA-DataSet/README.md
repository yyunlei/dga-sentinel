# DGA Dataset

This directory contains reference data for DGA (Domain Generation Algorithm) detection.

## Included Files

- `360_dga.txt` — Sample DGA domain list from 360 Security research

## Excluded Files (too large for git)

The following CSV files are **not included** in the repository:

| File | Size | Description |
|------|------|-------------|
| `dga_binary.csv` | ~6 MB | Binary classification dataset (DGA vs benign domains) |
| `dga_multi.csv` | ~6 MB | Multiclass dataset (per-family labels) |

## Obtaining the Full Datasets

These datasets can be reconstructed using the DGA generators in `dga_generate/`:

```bash
# Each family subdirectory contains a dga.py generator script
python dga_generate/conficker/dga.py
python dga_generate/locky/dga.py
# etc.
```

For benign domains, use publicly available datasets such as:
- Alexa Top 1M (archived)
- Majestic Million: https://majestic.com/reports/majestic-million
- Tranco list: https://tranco-list.eu/

## Format

The CSV files use the following schema:
```
domain,label
example.com,benign
xkajdf8s.net,dga
```
