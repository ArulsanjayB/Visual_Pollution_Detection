# CivicLens — Visual Pollution Detector

AI-powered Android/iOS application where citizens can report visual pollution issues such as potholes, abandoned vehicles, and construction debris using images and GPS location. The system uses YOLOv8 object detection along with Explainable AI techniques (Grad-CAM, LIME, SHAP, and ZooLime Fusion) to detect issues and provide transparent explanations for predictions.

Municipal staff can review reports, prioritize them, and resolve issues through a dedicated dashboard.

---

## System Architecture

```text
┌─────────────┐  HTTPS  ┌──────────────┐  calls  ┌────────────────┐
│ Mobile App  │────────▶│ FastAPI      │────────▶│ YOLOv8 + XAI   │
│ (React Native Expo) │ │ Backend      │        │ Inference Engine│
└─────────────┘◀────────└──────┬───────┘◀────────└────────────────┘
                               │
                               ▼
                     ┌────────────────────┐
                     │ Local JSON Storage │
                     │ + Image Storage    │
                     └────────────────────┘
                               ▲
                               │
                     ┌─────────┴──────────┐
                     │ Municipal Dashboard│
                     └────────────────────┘
```

---

# Features

## Citizen Features
- Capture/upload issue image
- Automatic GPS location fetching
- Submit issue reports
- Track report history
- Earn reward tokens after issue resolution

## Municipal Features
- View submitted complaints
- Priority-based issue sorting
- Mark issues as resolved
- Generate professional reports

## Admin Features
- Manage users
- Manage municipal staff
- System monitoring

---

# AI Features

## Object Detection
- YOLOv8 detects:
  - Potholes
  - Abandoned Vehicles
  - Construction Debris

## Explainable AI
This project integrates multiple explainability techniques:

### Grad-CAM
Highlights important regions responsible for prediction.

### LIME
Explains predictions using local perturbation analysis.

### SHAP
Used for additional feature importance explanation.

### ZooLime Fusion
Custom fusion algorithm combining Grad-CAM and LIME outputs.

Formula:

```math
Z = norm(α·G_smooth + (1-α)·L_smooth + β·(G·L))
```

Where:

- `G` → Grad-CAM output  
- `L` → LIME output  
- `β(G·L)` → boosts overlapping important regions

This improves explanation trustworthiness.

---

# Priority Scoring Formula

Municipal reports are prioritized using:

```math
P = 40(confidence) + 30(severity) + 20(class urgency) + 10(count factor)
```

Maximum score = 100.

---

# Tech Stack

## Frontend
- React Native Expo

## Backend
- FastAPI

## Machine Learning
- YOLOv8
- PyTorch
- OpenCV
- Albumentations

## Explainable AI
- Grad-CAM
- LIME
- SHAP

## Storage
- Local JSON storage
- Local file storage

---

# Project Structure

```text
civiclens/
│
├── backend/
│   ├── app/
│   ├── dashboard/
│   ├── storage/
│   ├── local_db/
│   └── requirements.txt
│
├── ml/
│   ├── train.py
│   ├── data_prep.py
│   ├── inference.py
│   ├── weights/
│   ├── runs/
│   └── xai/
│
├── mobile/
│   ├── App.js
│   ├── package.json
│   └── src/
│
├── setup.bat
├── setup.sh
├── prep_dataset.bat
├── prep_dataset.sh
├── train.bat
├── train.sh
├── run_backend.bat
└── run_backend.sh
```

---

# Dataset Information

The dataset is NOT included in this repository because GitHub has storage limitations.

Download dataset from:

https://drive.google.com/file/d/1xPazk0bT96FCRpHJydcfRDyTM8QU20zy/view?usp=drive_link

Dataset contains:
- Potholes
- Abandoned Vehicles
- Construction Debris

---

# Dataset Preparation

After downloading:

Place:

```text
combined_dataset_final.zip
```

inside the root folder.

Then run:

```bash
prep_dataset.bat
```

OR

```bash
prep_dataset.sh
```

This script:

- Extracts dataset
- Performs augmentation
- Balances classes
- Splits dataset into:
  - Train
  - Validation
  - Test

Generated folder:

```text
dataset/
└── yolo_dataset/
```

**Do NOT upload:**
- dataset/
- combined_dataset_final.zip
- venv/
- cache files

These should remain in `.gitignore`.

---

# Model Training

Run:

```bash
train.bat
```

OR

```bash
train.sh
```

This trains YOLOv8 on the prepared dataset.

---

# Running the Backend

```bash
run_backend.bat
```

OR

```bash
run_backend.sh
```

Backend runs on FastAPI.

---

# Running Mobile App

```bash
cd mobile
npm install
npx expo start
```

---

# Default Development Users

| Username | Role |
|----------|--------|
| dev_citizen | Citizen |
| dev_municipal | Municipal |
| dev_admin | Admin |

---

# Deep Learning Concepts Used

1. **CNN (convolutional neural networks)** — YOLOv8's backbone is a CSPDarknet-based feature extractor
2. **Transfer learning** — we start from COCO-pretrained weights (`yolov8s.pt`) and fine-tune on your pollution dataset. Pretrained weights give a huge head start because the early layers already know edges/textures/shapes.
3. **Object detection** — YOLOv8 outputs bounding boxes + class + confidence in a single forward pass
4. **Backpropagation** — used both (a) during training to update weights, and (b) during Grad-CAM to compute gradients of class score w.r.t. activation maps
5. **Loss functions** — YOLOv8 uses three: BBox regression (CIoU loss, weight 7.5), Classification (BCE, weight 0.5), Distribution Focal Loss (weight 1.5)
6. **Data augmentation** — both during `data_prep.py` (albumentations pipeline) and during training itself (mosaic, mixup, copy-paste, HSV shifts, random affine)
7. **Mixed precision (AMP)** — fp16 where safe, fp32 elsewhere — roughly 2× speedup on modern GPUs with no accuracy loss
8. **Cosine LR schedule** — learning rate smoothly decays from 0.001 to 0.00001 over training
---

# Documentation

Additional documents:

- `HOW_TO_RUN.md`
- `EXPLANATION.md`

## License

Educational use. YOLOv8 is AGPL-3.0 — consult https://docs.ultralytics.com/help/#license if deploying commercially.
