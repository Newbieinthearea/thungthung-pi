import time
from adafruit_servokit import ServoKit

# --- CONFIGURATION ---
kit = ServoKit(channels=16)

# 1. CHANNEL SETUP
slapper = kit.servo[0]   # Pin 0
gate    = kit.servo[15]  # Pin 15

# 2. CALIBRATION (THE FIX) 📐
# We shift the Center to 60. 
# This gives us room to subtract without going negative.
GATE_CENTER  = 60  
GATE_PLASTIC = GATE_CENTER + 40  # Result: 100° (Safe)
GATE_CAN     = GATE_CENTER - 40  # Result: 20° (Safe)

SLAP_HOME = 0
SLAP_HIT  = 110

# 3. TIMING ⏱️
GATE_DELAY = 0.3 
SLAP_SPEED = 0.5

print("✅ Sorter System Ready")
print(f"   Gate Center: {GATE_CENTER}°")
print(f"   Plastic Target: {GATE_PLASTIC}°")
print(f"   Can Target: {GATE_CAN}°")

# Move to Start Positions
gate.angle = GATE_CENTER
slapper.angle = SLAP_HOME

def perform_sort(item_type):
    # --- STEP 1: OPEN GATE ---
    if item_type == "p":
        print(f"   🔵 PLASTIC: Gate opening to {GATE_PLASTIC}°")
        gate.angle = GATE_PLASTIC
        
    elif item_type == "c":
        print(f"   🔴 CAN: Gate opening to {GATE_CAN}°")
        gate.angle = GATE_CAN
    
    time.sleep(GATE_DELAY)

    # --- STEP 2: SLAP ---
    print("   👊 Slapping!")
    slapper.angle = SLAP_HIT
    time.sleep(SLAP_SPEED)
    slapper.angle = SLAP_HOME
    
    # --- STEP 3: CLOSE GATE ---
    print("   🔄 Gate Closing")
    gate.angle = GATE_CENTER
    time.sleep(0.3) 

try:
    while True:
        item = input("\nScan Item (p/c/q) > ").lower().strip()
        
        if item in ["p", "c"]:
            perform_sort(item)
            
        elif item == "q":
            break

except KeyboardInterrupt:
    print("\n👋 Parking Motors...")
    gate.angle = GATE_CENTER
    slapper.angle = SLAP_HOME