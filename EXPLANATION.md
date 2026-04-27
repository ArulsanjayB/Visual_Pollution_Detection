# CivicLens: Step-by-Step Architecture & Explanation

This document provides a simple, step-by-step breakdown of how the entire CivicLens Visual Pollution Detector works from start to finish. It is designed to be easily understood so that you can confidently explain every part of the system to a panel or jury.

---

## 1. The Big Picture
CivicLens is a smart city application designed to identify and manage "visual pollution" like **Potholes**, **Abandoned Vehicles**, and **Construction Debris**. 

It consists of three main parts:
1. **The Citizen App:** A mobile app where people can take pictures of visual pollution.
2. **The AI Brain (Backend):** A server that receives the picture, uses Artificial Intelligence (AI) to find the pollution, and generates "explanations" so humans can trust the AI.
3. **The Municipal Dashboard:** A web portal where city workers see the reports, ordered by priority, and take action.

---

## 2. Step 1: The Citizen Submits a Report (Mobile App)
**What happens:**
A citizen sees a pile of construction debris. They open the CivicLens app on their phone, take a picture, and hit submit.

**How the code works:**
- The mobile app is built using **React Native**.
- When the citizen takes a photo, the app uses `expo-location` to grab their exact GPS coordinates (Latitude and Longitude).
- The app packages the photo and the GPS data into a "network request" and sends it over the internet to our backend server using an API (Application Programming Interface).

---

## 3. Step 2: The Server Receives the Data (Backend)
**What happens:**
The server gets the photo, saves it, and prepares it for the AI.

**How the code works:**
- The backend is built using **FastAPI** (a high-speed Python web framework).
- When the API receives the photo, it saves the original image to a local folder (`storage/images/`).
- It then passes the image path to our Machine Learning pipeline (`inference.py`) to do the heavy lifting.

---

## 4. Step 3: The AI Detects the Pollution (YOLOv8)
**What happens:**
The AI looks at the photo and says, *"I am 85% sure there is Construction Debris in the top-right corner."*

**How the code works:**
- We use an AI model called **YOLOv8 (You Only Look Once)**. It is a Convolutional Neural Network (CNN) specifically designed for object detection.
- **Why YOLO?** Because it looks at the entire image in one single pass, making it incredibly fast.
- The model was trained on thousands of images of potholes, vehicles, and debris. It learned to recognize the shapes, textures, and edges associated with these objects.
- The YOLO model outputs three things:
  1. A **Bounding Box** (coordinates drawing a square around the object).
  2. The **Class** (e.g., Construction Debris).
  3. A **Confidence Score** (e.g., 0.85 or 85%).
- *Note: Our system requires a minimum confidence of 35% to officially log the detection. If the AI is less than 35% sure, it ignores it.*

---

## 5. Step 4: Building Trust with Explainable AI (XAI)
**What happens:**
If an AI tells a city worker to dispatch a cleanup crew, the worker might ask, *"Why did the AI think this is debris? What if it's just a weird shadow?"* We use Explainable AI (XAI) to visually prove *why* the AI made its decision.

**How the code works:**
We use three different methods, plus our own custom algorithm, to explain the AI's "thought process."

### Method A: Grad-CAM (Gradient-weighted Class Activation Mapping)
- **How it works in plain English:** It creates a "heatmap" showing where the AI was "looking." Red/Yellow spots mean the AI paid a lot of attention to that area; Blue spots mean it ignored it.
- **How the code works:** It hooks into the final layers of the Neural Network. As the image passes through the network, Grad-CAM calculates the mathematical "gradients" (rates of change) to see which pixels had the biggest mathematical impact on the final prediction.

### Method B: LIME (Local Interpretable Model-agnostic Explanations)
- **How it works in plain English:** It breaks the image into puzzle pieces (superpixels). It then hides some puzzle pieces, runs the AI again, and sees if the AI changes its mind. If hiding a puzzle piece makes the AI change its mind, that piece is very important!
- **How the code works:** The code generates 500 slightly different, scrambled versions of the image. It feeds all 500 to the AI and uses statistics to figure out exactly which specific segments of the image are responsible for the detection.

### Method C: SHAP (SHapley Additive exPlanations)
- **How it works in plain English:** Based on Game Theory. It treats every pixel like a player in a game trying to win the "prediction." It calculates how much credit each pixel deserves for the final score.

### Method D: ZooLime (Our Custom Fusion Algorithm)
- **How it works in plain English:** Grad-CAM is fast but blurry. LIME is sharp but sometimes noisy. **ZooLime** takes the best of both worlds by mathematically merging them. It looks for areas where *both* Grad-CAM and LIME agree!
- **How the code works:**
  1. It gets the Grad-CAM heatmap.
  2. It gets the LIME heatmap.
  3. It applies a Gaussian Blur to smooth them out.
  4. It uses a mathematical formula: `Fusion = (Weight A * Grad-CAM) + (Weight B * LIME) + (Bonus if they both overlap)`.
  5. The resulting image is the ultimate, highly-reliable explanation.

---

## 6. Step 5: Scoring and Prioritization
**What happens:**
The city has limited resources. The system automatically calculates a "Priority Score" out of 100 so the city knows which reports to fix first.

**How the code works:**
In `report_service.py`, a mathematical formula calculates the score based on:
1. **Confidence (40% weight):** How sure the AI is.
2. **Severity (30% weight):** How large the object is compared to the image size.
3. **Class Urgency (20% weight):** Potholes get higher urgency because they damage cars, compared to abandoned vehicles.
4. **Quantity (10% weight):** Are there 5 potholes or just 1?

---

## 7. Step 6: The Municipal Dashboard & Admin Panel
**What happens:**
City workers log into a website. They see a list of reports sorted by priority. They can view the XAI images, generate PDF reports, and mark issues as "Resolved".

**How the code works:**
- The frontend dashboard uses HTML and JavaScript to fetch data from our FastAPI backend via `GET` requests.
- When a worker marks a report as "Resolved", the backend updates the database.
- **Reward System:** When the report is resolved, the backend automatically credits the Citizen who reported it with 10 "Reward Tokens" to gamify and encourage civic engagement!
- **Admin Panel:** Administrators have a special portal where they can view the history of specific users and delete spam or invalid reports.

---

## Summary for the Panel
If asked to summarize the project in one sentence:
*"CivicLens is an end-to-end smart city platform that empowers citizens to report visual pollution, uses state-of-the-art YOLOv8 object detection to identify the issues, applies our custom ZooLime algorithm to visually explain the AI's reasoning, and automatically prioritizes the workload for municipal authorities."*
