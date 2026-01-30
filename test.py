import cv2
import time

print("🔍 Searching for camera...")

# Try index 0 (standard) and 1 (common if index 0 is reserved)
for index in [0, 1, -1]:
    print(f"Testing index {index}...")
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"✅ SUCCESS! Camera found at index {index}")
            print(f"Resolution: {frame.shape[1]}x{frame.shape[0]}")
            cap.release()
            exit(0)
        else:
            print(f"❌ Opened index {index}, but failed to read frame.")
            cap.release()
    else:
        print(f"❌ Could not open index {index}")

print("🛑 FATAL: No working camera found.")