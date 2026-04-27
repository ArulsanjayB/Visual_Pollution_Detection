#!/bin/bash
cd "$(dirname "$0")"
[ -f combined_dataset_final.zip ] || { echo "[ERROR] combined_dataset_final.zip not found"; exit 1; }
[ -d venv ] || { echo "[ERROR] Run ./setup.sh first"; exit 1; }
source venv/bin/activate
cd ml
python data_prep.py --zip_path ../combined_dataset_final.zip --output_dir ../dataset
