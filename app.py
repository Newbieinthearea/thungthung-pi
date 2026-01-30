import os
import time
import io
import requests
import qrcode
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, send_file
from dotenv import load_dotenv
from supabase import create_client, Client

# --- IMPORT MODULES ---
from hardware.hardware_manager import HardwareManager
from ai.camera_manager import CameraManager

load_dotenv()
app = Flask(__name__)

# --- CONFIG ---
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
BASE_URL = os.getenv("BASE_URL", "http://localhost:3000") 
API_URL = f"{BASE_URL}/api/machine/kiosk"
PI_SECRET = os.getenv("PI_SECRET", "default")
BIN_ID = os.getenv("BIN_ID", "BIN_01")
MODEL_PATH = "model/ai-model-fp32-v2.tflite"

if not url or not key:
    raise ValueError("❌ Error: Missing Supabase credentials in .env file")

supabase: Client = create_client(url, key)
print(f"✅ Connected to Supabase for {BIN_ID}")

def sync_status(state, fill_level):
    try:
        data = {
            "status": state,
            "fillLevel": fill_level,
            "lastActive": datetime.now(timezone.utc).isoformat(),
            "isOnline": True
        }
        
        # Use the bin_id loaded from .env (matches Prisma 'id' field)
        supabase.table("Bin").update(data).eq("id", BIN_ID).execute()
        
    except Exception as e:
        print(f"⚠️ Cloud Sync Failed: {e}")
        
        
# --- INITIALIZE SYSTEMS ---
hw = HardwareManager()
cam = CameraManager(MODEL_PATH)

# --- GLOBAL STATE ---
state = { 
    "status": "IDLE", 
    "plastic": 0, "cans": 0, "other": 0, 
    "total_weight": 0, "last_item": "Ready", "last_weight": 0, 
    "transaction_id": None, "claim_secret": None 
}
qr_img_buffer = None

# ==========================================
# 🧠 THE BRAIN (Logic)
# ==========================================
def process_scan_request():
    try:
        # 1. PHYSICAL SENSING
        w_before = hw.get_weight()
        metal_found = hw.is_metal_detected()
        print(f"\n⚖️  Scale: {w_before:.2f}g | Metal: {metal_found}")

        # 2. CAPTURE
        hw.set_lights(hw.COLOR_FLASH)
        time.sleep(0.3)             
        frame = cam.capture_frame()
        hw.set_lights(hw.COLOR_OFF)      

        if frame is None: return None, 0

        # 3. AI PREDICTION
        label = cam.predict(frame)
        print(f"   [AI] Result: {label}")

        # --- HYBRID LOGIC & CONSTRAINTS ---
        
        # 🚫 50g WEIGHT LIMIT
        if w_before > 50.0:
            print(f"   ⚠️ REJECTED: Too heavy ({w_before:.1f}g)")
            label = "Other"

        # ❌ SENSOR CONFLICTS
        elif label == "Can" and not metal_found:
            print("   Correction: AI said Can, but No Metal -> Changing to Other")
            label = "Other"
        
        elif label == "Plastic" and metal_found:
            print("   Correction: Metal detected! Overriding AI to 'Can'")
            label = "Can"

        elif label == "Other" and metal_found:
            print("   Correction: Metal detected! Overriding 'Other' to 'Can'")
            label = "Can"

        print(f"   ✅ FINAL DECISION: {label}")

        # 4. DISPENSE
        hw.run_motor_sequence(label)
        
        # 5. CALC WEIGHT
        time.sleep(0.5)
        w_after = hw.get_weight()
        item_weight = abs(w_before - w_after)
        
        return label, item_weight

    except Exception as e:
        print(f"❌ Scan Error: {e}")
        return None, 0

# ==========================================
# 🌐 FLASK ROUTES
# ==========================================
@app.route('/')
def index(): return render_template('kiosk.html')

@app.route('/state')
def get_state():
    # 1. Initialize with default values (Safety First)
    bin_data = {"percent": 0, "is_full": False} 

    # 2. Try to get real data
    try:
        reading = hw.get_bin_level()
        if reading is not None:
            bin_data = reading
    except Exception as e:
        print(f"⚠️ Bin Sensor Error in route: {e}")
        # We keep the default 'bin_data' so the app doesn't crash

    # 3. Update global state response
    response = state.copy()
    response["bin_level"] = bin_data["percent"]
    response["bin_full"] = bin_data["is_full"]
    
    # 4. Sync to Supabase
    sync_status(state["status"], bin_data["percent"])
    
    return jsonify(response)

@app.route('/qr_image')
def get_qr_image(): 
    return send_file(qr_img_buffer, mimetype='image/png') if qr_img_buffer else ("", 404)

@app.route('/action/start', methods=['POST'])
def start():
    # 🛑 [NEW] CRITICAL BLOCKER: Check Bin First
    bin_status = hw.get_bin_level()
    if bin_status["is_full"]:
        print("🚫 Start Denied: Bin is Full")
        return jsonify({"error": "BIN_FULL"}), 400

    if not cam.start_camera(): 
        return jsonify({"error": "No Camera"}), 500
    
    hw.tare_scale()
    
    try:
        res = requests.post(API_URL, json={"action": "START", "binId": BIN_ID, "secret": PI_SECRET}, timeout=5)
        data = res.json()
        state["transaction_id"] = data.get("transactionId", f"OFF-{int(time.time())}")
        state["claim_secret"] = data.get("claimSecret", "offline")
    except:
        state["transaction_id"] = f"OFF-{int(time.time())}"
    
    state.update({"status": "RUNNING", "plastic": 0, "cans": 0, "other": 0, "total_weight": 0})
    
    # Sync bin status to Supabase
    bin_status = hw.get_bin_level()
    sync_status("RUNNING", bin_status["percent"])
    
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
        
        # Sync bin status to Supabase after each item
        bin_status = hw.get_bin_level()
        sync_status("RUNNING", bin_status["percent"])
        
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
    
    # Generate QR
    url = f"{BASE_URL}/claim/{state['transaction_id']}?secret={state['claim_secret']}"
    qr = qrcode.make(url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    global qr_img_buffer
    qr_img_buffer = buf
    
    # Sync bin status to Supabase
    bin_status = hw.get_bin_level()
    sync_status("SHOW_RESULT", bin_status["percent"])
    
    return jsonify({"success": True})

@app.route('/action/reset', methods=['POST'])
def reset():
    state["status"] = "IDLE"
    
    # Sync bin status to Supabase
    bin_status = hw.get_bin_level()
    sync_status("IDLE", bin_status["percent"])
    
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)