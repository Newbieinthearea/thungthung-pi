import sys
import importlib
import time
import board
import neopixel
import RPi.GPIO as GPIO
from adafruit_servokit import ServoKit
from hx711 import HX711

# --- COMPATIBILITY PATCH (For ServoKit on newer Python) ---
if "imp" not in sys.modules:
    sys.modules["imp"] = importlib

class HardwareManager:
    def __init__(self):
        # ==========================
        # 🔌 PIN CONFIGURATION (BCM)
        # ==========================
        self.PIXEL_PIN = board.D18
        self.NUM_PIXELS = 8
        
        self.WEIGHT_DT_PIN = 5      
        self.WEIGHT_SCK_PIN = 6     
        
        self.METAL_SENSOR_PIN = 26  
        
        self.BIN_TRIG_PIN = 23
        self.BIN_ECHO_PIN = 24

        # ==========================
        # ⚙️ SETTINGS
        # ==========================
        self.CALIBRATION_FACTOR = -1068.74
        self.BIN_HEIGHT_CM = 30      # 📏 MEASURE YOUR BIN DEPTH!
        self.BIN_FULL_THRESHOLD = 80 # % full to trigger alert

        # Servos
        self.SERVO_SORTER_CH = 15     
        self.SERVO_SLAPPER_CH = 0       
        
        # Angles
        self.ANGLE_IDLE = 60      
        self.ANGLE_PLASTIC = 95  
        self.ANGLE_CAN = 25     
        self.ANGLE_SLAP_REST = 65       
        self.ANGLE_SLAP_HIT = 160      

        # Colors
        self.COLOR_OFF = (0, 0, 0)
        self.COLOR_FLASH = (255, 150, 255) # Pinkish white
        self.COLOR_GREEN = (0, 255, 0)
        self.COLOR_RED = (255, 0, 0)

        # Initialize
        self.setup_drivers()

    def setup_drivers(self):
        GPIO.setmode(GPIO.BCM)

        # 1. LED Strip
        try:
            self.pixels = neopixel.NeoPixel(self.PIXEL_PIN, self.NUM_PIXELS, brightness=1.0, auto_write=False)
            self.set_lights(self.COLOR_OFF)
        except Exception as e: 
            print(f"⚠️ LED Error: {e}")
            self.pixels = None

        # 2. Servo Driver
        try:
            self.kit = ServoKit(channels=16)
            self.kit.servo[self.SERVO_SORTER_CH].set_pulse_width_range(500, 2500)
            self.kit.servo[self.SERVO_SLAPPER_CH].set_pulse_width_range(500, 2500)
            self.reset_motors()
            print("✅ Motor Driver Connected")
        except Exception as e: 
            print(f"⚠️ Motor Driver Error: {e}")
            self.kit = None

        # 3. Metal Sensor
        GPIO.setup(self.METAL_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # 4. Bin Sensor (Ultrasonic)
        GPIO.setup(self.BIN_TRIG_PIN, GPIO.OUT)
        GPIO.setup(self.BIN_ECHO_PIN, GPIO.IN)

        # 5. Weight Sensor
        try:
            self.hx = HX711(self.WEIGHT_DT_PIN, self.WEIGHT_SCK_PIN)
            self.hx.set_reading_format("MSB", "MSB")
            self.hx.set_reference_unit(self.CALIBRATION_FACTOR)
            self.hx.reset()
            self.hx.tare()
            print("✅ Weight Sensor Ready")
        except Exception as e: 
            print(f"⚠️ Weight Sensor Error: {e}")
            self.hx = None

    # ==========================
    # 💡 LIGHTS & SENSORS
    # ==========================
    def set_lights(self, color):
        if self.pixels:
            self.pixels.fill(color)
            self.pixels.show()

    def is_metal_detected(self):
        # Usually LOW means metal detected
        return GPIO.input(self.METAL_SENSOR_PIN) == 0

    def get_weight(self):
        if self.hx:
            try:
                val = self.hx.get_weight(5)
                return val if val > 0.5 else 0.0 
            except: return 0.0
        return 0.0

    def tare_scale(self):
        if self.hx:
            self.hx.reset()
            self.hx.tare()

    def get_bin_level(self):
        """Returns dict: {'percent': int, 'is_full': bool}"""
        try:
            # Trigger Pulse
            GPIO.output(self.BIN_TRIG_PIN, False)
            time.sleep(0.05)
            GPIO.output(self.BIN_TRIG_PIN, True)
            time.sleep(0.00001)
            GPIO.output(self.BIN_TRIG_PIN, False)

            # Listen for Echo
            pulse_start = time.time()
            pulse_end = time.time()
            timeout = time.time() + 0.1

            while GPIO.input(self.BIN_ECHO_PIN) == 0:
                pulse_start = time.time()
                # FIX: Return default dict instead of None
                if pulse_start > timeout: 
                    return {"percent": 0, "is_full": False, "error": True}

            while GPIO.input(self.BIN_ECHO_PIN) == 1:
                pulse_end = time.time()
                # FIX: Return default dict instead of None
                if pulse_end > timeout: 
                    return {"percent": 0, "is_full": False, "error": True}

            # Calculate Distance
            duration = pulse_end - pulse_start
            distance = duration * 17150
            
            # Calculate Percentage
            valid_dist = max(0, min(distance, self.BIN_HEIGHT_CM))
            fill_amount = self.BIN_HEIGHT_CM - valid_dist
            percent = (fill_amount / self.BIN_HEIGHT_CM) * 100
            
            return {
                "percent": int(percent),
                "is_full": percent >= self.BIN_FULL_THRESHOLD
            }
        except Exception as e:
            # If sensor fails, assume empty so we don't block the machine
            return {"percent": 0, "is_full": False}

    # ==========================
    # 🤖 MOTORS
    # ==========================
    def reset_motors(self):
        if not self.kit: return
        try:
            self.kit.servo[self.SERVO_SORTER_CH].angle = self.ANGLE_IDLE
            self.kit.servo[self.SERVO_SLAPPER_CH].angle = self.ANGLE_SLAP_REST
            time.sleep(0.5)
            self.kit.servo[self.SERVO_SORTER_CH].angle = None
            self.kit.servo[self.SERVO_SLAPPER_CH].angle = None
        except: pass

    def run_motor_sequence(self, label):
        if label == "Other" or not self.kit: return
        
        print(f"🤖 Motors: Sorting {label}...")
        target = self.ANGLE_PLASTIC if label == "Plastic" else self.ANGLE_CAN
        
        try:
            # 1. Move Sorter
            self.kit.servo[self.SERVO_SORTER_CH].angle = target
            time.sleep(0.5) 
            # 2. Slap!
            self.kit.servo[self.SERVO_SLAPPER_CH].angle = self.ANGLE_SLAP_HIT
            time.sleep(0.6) 
            # 3. Return Slapper
            self.kit.servo[self.SERVO_SLAPPER_CH].angle = self.ANGLE_SLAP_REST
            time.sleep(0.4) 
            # 4. Return Sorter
            self.kit.servo[self.SERVO_SORTER_CH].angle = self.ANGLE_IDLE
            time.sleep(0.5)
            # 5. Release (Save power)
            self.kit.servo[self.SERVO_SORTER_CH].angle = None
            self.kit.servo[self.SERVO_SLAPPER_CH].angle = None
        except Exception as e:
            print(f"❌ Motor Error: {e}")