#!/usr/bin/env python3
"""
Raspberry Pi Time-Lapse with PicamZero + LED/IR GPIO Control

Captures images every 10 minutes for 36 hours using PicamZero,
converts JPEG → TIFF, automatically numbers ZT001 → ZT216,
and controls LED + IR lights according to ZT schedule.

Author: Whitney Leach
Date: 2026-02-010
"""

import time
import os
import logging
from datetime import datetime, timedelta, time as dtime
from picamzero import Camera
from PIL import Image
import RPi.GPIO as GPIO

# ============================================
# USER SETTINGS
# ============================================

EXPERIMENT_ID = "1WL1"       # change to your experiment number  

CAPTURE_INTERVAL_SEC = 10 * 60      # 10 minutes
TOTAL_HOURS = 36

# GPIO pins
WHITE_LED_PIN = 17   # LIGHT
IR_LED_PIN = 27      # DARK

SAVE_DIR = f"/home/leachlab/Desktop/{EXPERIMENT_ID}"

# Real-time LD schedule
LIGHT_ON_TIME = dtime(7, 0)    # 07:00
LIGHT_OFF_TIME = dtime(19, 0)  # 19:00

# ============================================
# DERIVED VALUES
# ============================================

TOTAL_SECONDS = TOTAL_HOURS * 3600

# ============================================
# CAMERA SETUP
# ============================================

cam = Camera()
cam.resolution = (1920, 1080)

# ============================================
# GPIO SETUP
# ============================================

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)  # Suppress GPIO warnings
GPIO.setup(WHITE_LED_PIN, GPIO.OUT)
GPIO.setup(IR_LED_PIN, GPIO.OUT)

GPIO.output(WHITE_LED_PIN, GPIO.LOW)
GPIO.output(IR_LED_PIN, GPIO.LOW)

# ============================================
# DIRECTORY SETUP
# ============================================

os.makedirs(SAVE_DIR, exist_ok=True)

# ============================================
# LOGGING SETUP
# ============================================

# Set up logging to log to a file with time-stamped entries
log_filename = os.path.join(SAVE_DIR, f"{EXPERIMENT_ID}_experiment.log")
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# ============================================
# HELPER FUNCTIONS
# ============================================

def set_light_state(light_on: bool):
    """Set light state (white LED / IR)."""
    GPIO.output(WHITE_LED_PIN, GPIO.HIGH if light_on else GPIO.LOW)
    GPIO.output(IR_LED_PIN, GPIO.LOW if light_on else GPIO.HIGH)

    state = "LIGHT (white)" if light_on else "DARK (IR)"
    logging.info(f"Light state: {state}")
    print(f"[{datetime.now()}] Light state: {state}")

def is_light_phase(now: datetime) -> bool:
    """Check if the current time is in the light phase."""
    return LIGHT_ON_TIME <= now.time() < LIGHT_OFF_TIME

def next_zt0(now: datetime) -> datetime:
    """Get the next real-time 07:00 (ZT0)."""
    today_zt0 = datetime.combine(now.date(), LIGHT_ON_TIME)
    if now < today_zt0:
        return today_zt0
    else:
        return today_zt0 + timedelta(days=1)

def capture_and_convert(now, zt_frame, current_light_state):
    """Capture image, convert to TIFF, and delete the JPG."""
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    base_name = f"{EXPERIMENT_ID}_ZT{zt_frame:03d}_{timestamp}"

    jpg_path = os.path.join(SAVE_DIR, base_name + ".jpg")
    tiff_path = os.path.join(SAVE_DIR, base_name + ".tiff")

    cam.take_photo(jpg_path)

    with Image.open(jpg_path) as img:
        img.save(tiff_path, format="TIFF")

    os.remove(jpg_path)

    # Log GPIO and camera parameters for reproducibility
    logging.info(
        f"ZT{zt_frame:03d} | Light={current_light_state} | "
        f"Shutter={cam.shutter_speed} | ISO={cam.iso}"
    )
    print(f"Saved {base_name}: {tiff_path}")
    logging.info(f"Saved {base_name}: {tiff_path}")

# ============================================
# WAIT FOR ZT0 (07:00)
# ============================================

now = datetime.now()
start_time = next_zt0(now)

logging.info(f"Current time: {now}")
logging.info(f"Waiting until ZT0 (07:00): {start_time}")

print(f"Waiting until ZT0 (07:00): {start_time}")

# Ensure lights are OFF / safe while waiting
set_light_state(False)

while datetime.now() < start_time:
    time.sleep(30)

# ============================================
# MAIN EXPERIMENT LOOP
# ============================================

def run_experiment():
    experiment_start = datetime.now()
    experiment_end = experiment_start + timedelta(hours=TOTAL_HOURS)

    # Track the current light state to avoid repeated GPIO updates
    current_light_state = None

    # Track if the exposure settings are locked
    exposure_locked = False

    # Track the last captured frame to prevent redundant captures
    last_captured_frame = -1

    logging.info(f"Experiment started at ZT0: {experiment_start}")

    while datetime.now() < experiment_end:
        now = datetime.now()

        # ---- Compute Elapsed Time in Seconds ----
        elapsed_sec = (now - experiment_start).total_seconds()

        # ---- Compute Frame Index (ZT) ----
        frame_index = int(elapsed_sec // CAPTURE_INTERVAL_SEC)

        # ---- Compute ZT Frame ----
        zt_frame = frame_index + 1

        logging.info(f"Elapsed time: {elapsed_sec}s, ZT{zt_frame:03d}")

        # ---- LIGHT STATE (REAL TIME) ----
        light_phase = is_light_phase(now)

        if current_light_state != light_phase:
            # Light phase has changed, update GPIO and lock exposure
            set_light_state(light_phase)
            current_light_state = light_phase
            exposure_locked = False  # Reset exposure lock

        if not exposure_locked:
            # Set exposure settings based on light phase (only on first transition)
            if light_phase:
                # Light phase (White LED)
                cam.shutter_speed = 10000  # Example value for daylight
                cam.iso = 100               # Low ISO for daylight
            else:
                # Dark phase (IR)
                cam.shutter_speed = 30000  # Example value for IR
                cam.iso = 1600             # Higher ISO for low light

            # Lock the exposure once the settings are applied
            exposure_locked = True

            # Exposure settle delay (to ensure exposure settings are stable)
            time.sleep(0.2)

        # ---- IMAGE CAPTURE ----
        if frame_index > last_captured_frame:
            capture_and_convert(now, zt_frame, current_light_state)
            last_captured_frame = frame_index  # Update the last captured frame

        time.sleep(5)

# ============================================
# RUN + CLEANUP
# ============================================

try:
    run_experiment()
except KeyboardInterrupt:
    logging.info("Experiment interrupted by user.")
    print("Experiment interrupted by user.")
finally:
    GPIO.output(WHITE_LED_PIN, GPIO.LOW)
    GPIO.output(IR_LED_PIN, GPIO.LOW)
    GPIO.cleanup()  # Clean up GPIO pins
    camera.close()  # Close the camera safely
    logging.info("Experiment finished cleanly.")
    print("Experiment finished cleanly.")
