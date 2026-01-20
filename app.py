import sys
import importlib
import os
import time
import io
import threading

# --- PATCH: Fix for Python 3.13 ---
if "imp" not in sys.modules:
    sys.modules["imp"] = importlib
# ----------------------------------

os.environ["OPENCV_LOG_LEVEL"] = "OFF"

import cv2
import numpy as np
import requests
import qrcode
from flask import Flask, render_template, jsonify, send_file
from dotenv import load_dotenv

# ----------------------------------
# OpenCV / Pi stability
# ----------------------------------
cv2.setNumThreads(1)

# ----------------------------------
# CONFIG
# ----------------------------------
load_dotenv()
app = Flask(__name__)

if not os.path.exists("static"):
    os.makedirs("static")

CLOUD_URL = os.getenv("CLOUD_URL", "http://localhost:3000/api/machine/kiosk")
PI_SECRET = os.getenv("PI_SECRET", "default")
BIN_ID = os.getenv("BIN_ID", "BIN_01")
MODEL_PATH = "model/ai-model-fp32.tflite"

# ----------------------------------
# AI MODEL
# ----------------------------------
print("⏳ Loading AI Model...")
import tensorflow as tf
interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
print("✅ Model Ready")

# ----------------------------------
# STATE
# ----------------------------------
state = {
    "status": "IDLE",
    "transaction_id": None,
    "claim_secret": None,
    "plastic": 0,
    "cans": 0,
    "last_item": "Ready"
}

qr_img_buffer = None

# ----------------------------------
# CAMERA GLOBALS
# ----------------------------------
global_cap = None
latest_frame = None
camera_running = False
camera_lock = threading.Lock()

# ----------------------------------
# CAMERA THREAD
# ----------------------------------
def camera_loop():
    global latest_frame, camera_running

    while camera_running:
        if global_cap is None or not global_cap.isOpened():
            time.sleep(0.5)
            continue

        ret, frame = global_cap.read()
        if ret:
            with camera_lock:
                latest_frame = frame
        else:
            print("⚠️ Camera stalled, restarting...")
            restart_camera()
            time.sleep(1)

# ----------------------------------
# CAMERA CONTROL
# ----------------------------------
def start_camera():
    global global_cap, camera_running

    if camera_running:
        return

    for index in [0, 1, 2]:
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                global_cap = cap
                camera_running = True
                threading.Thread(
                    target=camera_loop,
                    daemon=True
                ).start()
                print(f"✅ Camera started at index {index}")
                return

        cap.release()

    print("❌ No USB camera detected")

def stop_camera():
    global global_cap, camera_running

    camera_running = False
    time.sleep(0.2)

    if global_cap:
        global_cap.release()
        global_cap = None
        print("🛑 Camera released")

def restart_camera():
    stop_camera()
    time.sleep(1)
    start_camera()

def capture_frame():
    with camera_lock:
        if latest_frame is None:
            return None
        return latest_frame.copy()

# ----------------------------------
# AI PREDICTION
# ----------------------------------
def predict_image(frame):
    cv2.imwrite("static/detected.jpg", frame)

    img = cv2.resize(frame, (224, 224))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    input_data = np.expand_dims(img.astype("float32"), axis=0)
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()
    output_data = interpreter.get_tensor(output_details[0]['index'])

    p = float(output_data[0][0])
    return "Plastic" if p >= 0.5 else "Can"

# ----------------------------------
# QR
# ----------------------------------
def generate_qr(link):
    global qr_img_buffer

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    qr_img_buffer = buf

# ----------------------------------
# ROUTES
# ----------------------------------
@app.route('/')
def index():
    return render_template('kiosk.html')

@app.route('/state')
def get_state():
    return jsonify(state)

@app.route('/qr_image')
def get_qr_image():
    if qr_img_buffer:
        return send_file(qr_img_buffer, mimetype='image/png')
    return "", 404

# ----------------------------------
# ACTIONS
# ----------------------------------
@app.route('/action/start', methods=['POST'])
def start():
    try:
        state["plastic"] = 0
        state["cans"] = 0
        state["last_item"] = "Ready"

        start_camera()

        res = requests.post(
            CLOUD_URL,
            json={"action": "START", "binId": BIN_ID, "secret": PI_SECRET},
            timeout=5
        )
        data = res.json()

        if data.get("success"):
            state["status"] = "RUNNING"
            state["transaction_id"] = data["transactionId"]
            state["claim_secret"] = data["claimSecret"]
            return jsonify({"success": True})

    except Exception as e:
        print("START ERROR:", e)

    return jsonify({"error": "Failed"})

@app.route('/action/scan', methods=['POST'])
def scan():
    if state["status"] != "RUNNING":
        return jsonify({"error": "IDLE"})

    frame = capture_frame()
    if frame is None:
        return jsonify({"error": "No frame"})

    try:
        label = predict_image(frame)
        state["last_item"] = label

        if label == "Plastic":
            state["plastic"] += 1
        else:
            state["cans"] += 1

        return jsonify({"success": True, "label": label})

    except Exception as e:
        print("SCAN ERROR:", e)
        return jsonify({"error": str(e)})

@app.route('/action/stop', methods=['POST'])
def stop():
    if state["status"] != "RUNNING":
        return jsonify({"error": "IDLE"})

    try:
        stop_camera()

        requests.post(CLOUD_URL, json={
            "action": "STOP",
            "transactionId": state["transaction_id"],
            "plastic": state["plastic"],
            "cans": state["cans"],
            "secret": PI_SECRET
        })

        base = CLOUD_URL.split("/api")[0]
        base = base.replace("/api/machine/kiosk", "").replace("/api", "")
        link = f"{base}/claim/{state['transaction_id']}?secret={state['claim_secret']}"

        generate_qr(link)
        state["status"] = "SHOW_RESULT"

        return jsonify({"success": True})

    except Exception as e:
        print("STOP ERROR:", e)
        return jsonify({"error": "Failed"})

@app.route('/action/reset', methods=['POST'])
def reset():
    state["status"] = "IDLE"
    stop_camera()
    return jsonify({"success": True})

# ----------------------------------
# MAIN
# ----------------------------------
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )
