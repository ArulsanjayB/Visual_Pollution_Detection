#!/bin/bash
cd "$(dirname "$0")"
[ -f dataset/yolo_dataset/dataset.yaml ] || { echo "[ERROR] Run ./prep_dataset.sh first"; exit 1; }
source venv/bin/activate
cd ml
python train.py --data ../dataset/yolo_dataset/dataset.yaml --model yolov8s --epochs 60
