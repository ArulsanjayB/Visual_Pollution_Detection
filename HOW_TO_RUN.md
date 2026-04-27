# How to Run CivicLens

This guide will walk you through setting up and running the CivicLens Visual Pollution Detector from scratch.

## Prerequisites
1. **Python 3.11** (Recommended. 3.12 works too, but PyTorch support is best on 3.11).
2. **Node.js** (LTS version 20.x or higher) for the mobile app.
3. **NVIDIA GPU** (Optional but highly recommended for training the ML model).
4. **Expo Go** app installed on your smartphone (Android or iOS).

---

## Step 1: Automated Setup
We have provided automated scripts to install all Python dependencies and set up your environment.

**On Windows:**
1. Open the project folder in VS Code.
2. Open the terminal and run:
   ```cmd
   setup.bat
   ```
   *This will create a virtual environment (`venv`), install PyTorch with CUDA support, and install FastAPI, YOLOv8, and other requirements.*

**On Linux/Mac:**
Run `./setup.sh` instead.

---

## Step 2: Prepare the Dataset (Optional if you already have a trained model)
If you want to train the AI yourself, you need to prepare the dataset.

1. Ensure `combined_dataset_final.zip` is in the root directory.
2. Run the preparation script:
   ```cmd
   prep_dataset.bat
   ```
   *This extracts the images, performs data augmentation (flipping, color adjustments, etc.) to balance the classes, and creates a YOLO-compatible dataset folder.*

---

## Step 3: Train the AI Model (Optional)
To train the YOLOv8 object detection model on your prepared dataset:

1. Run the training script:
   ```cmd
   train.bat
   ```
   *The script automatically detects your GPU's memory and selects the optimal batch size. It will train for 60 epochs and save the best weights to `ml/runs/visual_pollution_v1/weights/best.pt`.*

---

## Step 4: Start the Backend Server
The backend is the brain of the system, handling API requests, database storage, and AI inference.

1. Run the backend script:
   ```cmd
   run_backend.bat
   ```
2. The server will start on `http://0.0.0.0:8000`.
3. Keep this terminal window **open**.

**Useful Links:**
- Municipal Web Dashboard: http://localhost:8000/dashboard/
- Interactive API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/health

---

## Step 5: Start the Mobile App
The mobile app is built with React Native and Expo.

1. Open a **new** terminal window (do not close the backend terminal).
2. Find your computer's IP address by running `ipconfig` (Windows) or `ifconfig` (Mac/Linux). Look for the IPv4 Address (e.g., `192.168.1.5`).
3. Open `mobile/app.json` and update the `apiBaseUrl` with your IP address:
   ```json
   "extra": {
     "apiBaseUrl": "http://192.168.1.5:8000"
   }
   ```
4. Navigate to the mobile folder and start the Expo server:
   ```cmd
   cd mobile
   npm install
   npx expo start
   ```
5. A QR code will appear in the terminal.
6. Make sure your phone is connected to the **same Wi-Fi network** as your computer.
7. Open the **Expo Go** app on your phone and scan the QR code.
8. The app will build and open on your phone!

---

## Step 6: Using the System
1. **As a Citizen:** In the mobile app, click the "Citizen" quick-login. Tap "Report Pollution", take a photo of a pothole, abandoned vehicle, or construction debris, and hit submit!
2. **As a Municipal Worker:** Open http://localhost:8000/dashboard/ on your computer. Log in as `municipal` (or use the dev buttons). You will see the citizen's report automatically categorized, prioritized, and explained using Explainable AI (XAI).
3. **As an Admin:** You can manage users, view specific user report histories, and delete invalid reports from the Admin panel.
