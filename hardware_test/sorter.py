def sort_plastic(self):
        if not self.servo: return
        print("⚙️ Hardware: Sorting PLASTIC (Left)")
        self.servo.angle = -90
        sleep(1.0)
        self.servo.value = None # <--- Add this to stop shaking
        self.reset()

    def sort_can(self):
        if not self.servo: return
        print("⚙️ Hardware: Sorting CAN (Right)")
        self.servo.angle = 90
        sleep(1.0)
        self.servo.value = None # <--- Add this to stop shaking
        self.reset()

    def reset(self):
        if not self.servo: return
        self.servo.angle = 0
        sleep(0.5)
        self.servo.value = None # <--- Add this to stop shaking