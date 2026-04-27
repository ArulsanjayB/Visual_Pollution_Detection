import os
import sys
import torch

# Add ml folder to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from inference import PollutionInferenceEngine

def main():
    engine = PollutionInferenceEngine("runs/visual_pollution_v1/weights/best.pt")
    
    # Check if there's any image we can use
    test_image = "../dataset/images/test/Potholes/pothole_1.jpg"
    if not os.path.exists(test_image):
        # find an image
        import glob
        images = glob.glob("../dataset/**/*.jpg", recursive=True)
        if not images:
            print("No test images found.")
            return
        test_image = images[0]
    
    print(f"Using image: {test_image}")
    try:
        res = engine.run(test_image, xai_mode="gradcam")
        print("Success!")
        print("XAI Method:", res["xai"]["method"])
        if "error" in res["xai"]["metadata"]:
            print("ERROR IN XAI:", res["xai"]["metadata"]["error"])
        else:
            print("No errors in XAI.")
    except Exception as e:
        print("FAILED:", e)

if __name__ == "__main__":
    main()
