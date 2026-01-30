import board
import neopixel
import time

# Pin 12 is board.D18
pixel_pin = board.D18
num_pixels = 8  # You said you have 8 LEDs

pixels = neopixel.NeoPixel(pixel_pin, num_pixels, brightness=0.3, auto_write=False)

def wheel(pos):
    # Generates rainbow colors
    if pos < 0 or pos > 255:
        r = g = b = 0
    elif pos < 85:
        r = int(pos * 3)
        g = int(255 - pos * 3)
        b = 0
    elif pos < 170:
        pos -= 85
        r = int(255 - pos * 3)
        g = 0
        b = int(pos * 3)
    else:
        pos -= 170
        r = 0
        g = int(pos * 3)
        b = int(255 - pos * 3)
    return (r, g, b)

print("🌈 LED Rainbow Test Running...")
print("   (Press Ctrl+C to stop)")

try:
    while True:
        for j in range(255):
            for i in range(num_pixels):
                pixel_index = (i * 256 // num_pixels) + j
                pixels[i] = wheel(pixel_index & 255)
            pixels.show()
            time.sleep(0.01)
            
except KeyboardInterrupt:
    pixels.fill((0, 0, 0))
    pixels.show()