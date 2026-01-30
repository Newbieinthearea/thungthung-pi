import sys
import importlib
import os
import time
import io
import threading
import traceback
import RPi.GPIO as GPIO
import board
import neopixel
from adafruit_servokit import ServoKit 
from hx711 import HX711 

# --- COMPATIBILITY PATCH ---
if "imp" not in sys.modules:
    sys.modules["imp"] = importlib

os.environ["OPENCV_LOG_LEVEL"] = "OFF"
import cv2
import numpy as np
import requests
import qrcode
from flask import Flask, render_template, jsonify, send_file
from dotenv import load_dotenv
import tensorflow as tf

load_dotenv()
app = Flask(__name__)

# ==========================================
# 🌐 CONFIGURATION
# ==========================================
BASE_URL = os.getenv("BASE_URL", "http://localhost:3000") 
API_URL = f"{BASE_URL}/api/machine/kiosk"
PI_SECRET = os.getenv("PI_SECRET", "default")
BIN_ID = os.getenv("BIN_ID", "BIN_01")

MODEL_PATH = "model/ai-model-fp32-v2.tflite"

# --- Pins (BCM Numbering) ---
PIXEL_PIN = board.D18    
NUM_PIXELS = 8
LED_BRIGHTNESS = 1.0

WEIGHT_DT_PIN = 5      # Physical 29
WEIGHT_SCK_PIN = 6     # Physical 31
CALIBRATION_FACTOR = -1068.74  

METAL_SENSOR_PIN = 26  # Physical 37

SERVO_SORTER_CH = 15     
SERVO_SLAPPER_CH = 0       

# --- Motor Angles ---
ANGLE_SORTER_IDLE = 60      
ANGLE_SORTER_PLASTIC = ANGLE_SORTER_IDLE + 35  
ANGLE_SORTER_CAN = ANGLE_SORTER_IDLE - 35     

ANGLE_SLAP_REST = 65       
ANGLE_SLAP_HIT = 160      

# 🎨 COLORS
COLOR_OFF = (0, 0, 0)
COLOR_FLASH_WHITE = (255, 150, 255) 

# ==========================================
# 🛠️ HARDWARE FUNCTIONS
# ==========================================
pixels = None
kit = None
hx = None

def setup_hardware():
    global pixels, kit, hx
    GPIO.setmode(GPIO.BCM)

    # 1. LED
    try:
        pixels = neopixel.NeoPixel(PIXEL_PIN, NUM_PIXELS, brightness=LED_BRIGHTNESS, auto_write=False, pixel_order=neopixel.RGB)
        set_lights(COLOR_OFF)
    except Exception as e:
        print(f"⚠️ LED Error: {e}")

    # 2. Servos
    try:
        kit = ServoKit(channels=16)
        kit.servo[SERVO_SORTER_CH].set_pulse_width_range(500, 2500)
        kit.servo[SERVO_SLAPPER_CH].set_pulse_width_range(500, 2500)
        reset_motors()
        print("✅ Motor Driver Connected")
    except Exception as e:
        print(f"⚠️ Motor Driver Error: {e}")

    # 3. Metal Sensor
    try:
        GPIO.setup(METAL_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print("✅ Metal Sensor Ready")
    except Exception as e:
        print(f"⚠️ Metal Sensor Error: {e}")

    # 4. Weight Sensor
    try:
        hx = HX711(WEIGHT_DT_PIN, WEIGHT_SCK_PIN)
        hx.set_reading_format("MSB", "MSB")
        hx.set_reference_unit(CALIBRATION_FACTOR)
        hx.reset()
        hx.tare()
        print("✅ Weight Sensor Ready")
    except Exception as e:
        print(f"⚠️ Weight Sensor Error: {e}")

def set_lights(color):
    if pixels:
        pixels.fill(color)
        pixels.show()

def reset_motors():
    if not kit: return
    try:
        kit.servo[SERVO_SORTER_CH].angle = ANGLE_SORTER_IDLE
        kit.servo[SERVO_SLAPPER_CH].angle = ANGLE_SLAP_REST
        time.sleep(0.5)
        kit.servo[SERVO_SORTER_CH].angle = None
        kit.servo[SERVO_SLAPPER_CH].angle = None
    except: pass

def get_weight():
    if hx:
        try:
            val = hx.get_weight(5)
            return val if val > 0.5 else 0.0 
        except: return 0.0
    return 0.0

def is_metal_detected():
    return GPIO.input(METAL_SENSOR_PIN) == 0

def run_motor_sequence(label):
    if label == "Other" or not kit: return
    
    target_angle = ANGLE_SORTER_PLASTIC if label == "Plastic" else ANGLE_SORTER_CAN
    
    kit.servo[SERVO_SORTER_CH].angle = target_angle
    time.sleep(0.5) 
    kit.servo[SERVO_SLAPPER_CH].angle = ANGLE_SLAP_HIT
    time.sleep(0.6) 
    kit.servo[SERVO_SLAPPER_CH].angle = ANGLE_SLAP_REST
    time.sleep(0.4) 
    kit.servo[SERVO_SORTER_CH].angle = ANGLE_SORTER_IDLE
    time.sleep(0.5)
    kit.servo[SERVO_SORTER_CH].angle = None
    kit.servo[SERVO_SLAPPER_CH].angle = None

# ==========================================
# 🧠 AI ENGINE
# ==========================================
try:
    interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    model_h, model_w = input_details[0]['shape'][1], input_details[0]['shape'][2]
    input_index = input_details[0]['index']
    ai_lock = threading.Lock()
    print(f"✅ AI Model Loaded")
except Exception as e:
    print(f"❌ AI Error: {e}")
    sys.exit(1)

global_cap = None
latest_frame = None
camera_running = False
camera_lock = threading.Lock()

def start_camera():
    global global_cap, camera_running
    if camera_running and global_cap: return True
    for idx in [0, 1, -1]:
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                global_cap = cap
                camera_running = True
                threading.Thread(target=camera_loop, daemon=True).start()
                return True
        except: continue
    return False

def camera_loop():
    global latest_frame
    while camera_running and global_cap:
        ret, frame = global_cap.read()
        if ret:
            with camera_lock: latest_frame = frame
        else: time.sleep(0.1)

def capture_frame():
    with camera_lock: return latest_frame.copy() if latest_frame is not None else None

# ==========================================
# 🔄 CORE LOGIC
# ==========================================
state = { "status": "IDLE", "plastic": 0, "cans": 0, "other": 0, "total_weight": 0, "last_item": "Ready", "last_weight": 0, "transaction_id": None, "claim_secret": None }
qr_img_buffer = None

def process_scan_request():
    try:
        # 1. PHYSICAL SENSING
        w_before = get_weight()
        metal_found = is_metal_detected()
        
        # 🧪 WEIGHT DEBUG
        print(f"\n⚖️  DEBUG: Current Scale Weight: {w_before:.2f}g")

        # 2. CAPTURE
        set_lights(COLOR_FLASH_WHITE)
        time.sleep(0.3)             
        frame = capture_frame()
        set_lights(COLOR_OFF)      

        if frame is None: return None, 0

        # 3. AI PREDICTION
        with ai_lock:
            img = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (model_w, model_h))
            img_array = np.expand_dims(img.astype("float32"), axis=0)
            interpreter.set_tensor(input_index, img_array)
            interpreter.invoke()
            probs = interpreter.get_tensor(output_details[0]['index'])[0]
            
            pred_idx = np.argmax(probs)
            label = "Can" if pred_idx == 0 else "Plastic" if pred_idx == 2 else "Other"

            # --- HYBRID LOGIC & CONSTRAINTS ---
            print(f"   [Logic] AI Result: {label} | Metal Sensor: {metal_found}")

            # 🚫 50g WEIGHT LIMIT
            print(f"   [Logic] AI Result: {label} | Metal Sensor: {metal_found}")

    # 🚫 Weight limit
        if w_before > 50.0:
            print(f"   ⚠️ REJECTED: Item too heavy ({w_before:.1f}g > 50g)")
            label = "Other"

        # ❌ AI & Sensor DISAGREE → reject
        elif label == "Can" and not metal_found:
            print("   ❌ REJECTED: AI says Can but no metal detected")
            label = "Other"

        elif label == "Plastic" and metal_found:
            print("   ❌ REJECTED: AI says Plastic but metal detected")
            label = "Other"

        # ✅ AI & Sensor AGREE → accept
        else:
            print("   ✅ ACCEPTED: AI and Sensor agree")

        # 4. DISPENSE
        run_motor_sequence(label)
        
        # 5. FINAL WEIGHT CALCULATION
        time.sleep(0.5)
        w_after = get_weight()
        item_weight = abs(w_before - w_after)
        
        return label, item_weight
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, 0

# ==========================================
# 🌐 FLASK ROUTES
# ==========================================

@app.route('/')
def index():
    # This looks for 'templates/kiosk.html'
    return render_template('kiosk.html')
@app.route('/state')
def get_state(): return jsonify(state)

@app.route('/qr_image')
def get_qr_image(): return send_file(qr_img_buffer, mimetype='image/png') if qr_img_buffer else ("", 404)

@app.route('/action/start', methods=['POST'])
def start():
    if not start_camera(): return jsonify({"error": "No Camera"}), 500
    if hx: 
        hx.reset()
        hx.tare()
    try:
        res = requests.post(API_URL, json={"action": "START", "binId": BIN_ID, "secret": PI_SECRET}, timeout=5)
        data = res.json()
        state["transaction_id"] = data.get("transactionId", f"OFF-{int(time.time())}")
        state["claim_secret"] = data.get("claimSecret", "offline")
    except:
        state["transaction_id"] = f"OFF-{int(time.time())}"
    
    state.update({"status": "RUNNING", "plastic": 0, "cans": 0, "other": 0, "total_weight": 0})
    return jsonify({"success": True})

@app.route('/action/scan', methods=['POST'])
def scan():
    label, weight = process_scan_request()
    if label:
        state["last_item"], state["last_weight"] = label, weight
        state["total_weight"] += weight
        if label == "Plastic": state["plastic"] += 1
        elif label == "Can": state["cans"] += 1
        else: state["other"] += 1
        return jsonify({"success": True, "label": label, "weight": round(weight, 1)})
    return jsonify({"error": "Scan Failed"}), 500

@app.route('/action/stop', methods=['POST'])
def stop():
    state["status"] = "SHOW_RESULT"
    try:
        requests.post(API_URL, json={
            "action": "STOP", 
            "transactionId": state["transaction_id"], 
            "plastic": state["plastic"], 
            "cans": state["cans"], 
            "secret": PI_SECRET
        }, timeout=3)
    except: pass
    
    url = f"{BASE_URL}/claim/{state['transaction_id']}?secret={state['claim_secret']}"
    qr = qrcode.make(url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    global qr_img_buffer
    qr_img_buffer = buf
    return jsonify({"success": True})

@app.route('/action/reset', methods=['POST'])
def reset():
    state["status"] = "IDLE"
    return jsonify({"success": True})

if __name__ == '__main__':
    setup_hardware()
    app.run(host='0.0.0.0', port=5000, debug=False)