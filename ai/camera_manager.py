import os
import time
import threading
import numpy as np

# Force OpenCV Log Level off before importing
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
import cv2
import tensorflow as tf

class CameraManager:
    def __init__(self, model_path):
        self.model_path = model_path
        self.lock = threading.Lock()
        self.cap = None
        self.latest_frame = None
        self.running = False

        # Load AI Model
        try:
            self.interpreter = tf.lite.Interpreter(model_path=model_path)
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            
            # Get expected input shape (e.g., 224x224)
            self.model_h = self.input_details[0]['shape'][1]
            self.model_w = self.input_details[0]['shape'][2]
            self.input_index = self.input_details[0]['index']
            self.output_index = self.output_details[0]['index']
            print(f"✅ AI Model Loaded")
        except Exception as e:
            print(f"❌ AI Init Error: {e}")
            self.interpreter = None

    def start_camera(self):
        if self.running and self.cap: return True
        
        # Try indices 0, 1, -1 to find a camera
        for idx in [0, 1, -1]:
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                if cap.isOpened():
                    self.cap = cap
                    self.running = True
                    threading.Thread(target=self._camera_loop, daemon=True).start()
                    print(f"📷 Camera started on index {idx}")
                    return True
            except: continue
        return False

    def _camera_loop(self):
        while self.running and self.cap:
            ret, frame = self.cap.read()
            if ret:
                with self.lock: 
                    self.latest_frame = frame
            else: 
                time.sleep(0.1)

    def capture_frame(self):
        with self.lock: 
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def predict(self, frame):
        if not self.interpreter or frame is None:
            return "Error"

        try:
            # Preprocess: Resize & Convert to float32
            img = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (self.model_w, self.model_h))
            img_array = np.expand_dims(img.astype("float32"), axis=0)

            # Inference
            self.interpreter.set_tensor(self.input_index, img_array)
            self.interpreter.invoke()
            probs = self.interpreter.get_tensor(self.output_index)[0]
            
            # Map index to label
            pred_idx = np.argmax(probs)
            # 0=Can, 1=Other, 2=Plastic (Based on your previous code logic)
            if pred_idx == 0: return "Can"
            if pred_idx == 2: return "Plastic"
            return "Other"

        except Exception as e:
            print(f"AI Prediction Error: {e}")
            return "Other"