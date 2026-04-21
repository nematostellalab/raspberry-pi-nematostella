# ============================================
# 36-hour Image Capture with 12:12 LD 
# Captures image every 10 minutes for 36 hours
# Starts image capturea at next 7am 
# Updated: April 21, 2026
# Author: Whitney Leach
# ============================================

import time
import os
import logging
import csv
from datetime import datetime, timedelta, time as dtime
from picamzero import Camera
from PIL import Image
import RPi.GPIO as GPIO

# ============================================
# USER SETTINGS
# ============================================

EXPERIMENT_ID = "1WL4"

CAPTURE_INTERVAL_SEC = 10 * 60   # 10 minutes
TOTAL_HOURS = 36

WHITE_LED_PIN = 14   # BCM numbering
IR_LED_PIN = 15

SAVE_DIR = f"/home/leachlab/Desktop/{EXPERIMENT_ID}"

LIGHT_ON_TIME = dtime(7, 0)     # 7:00 AM (ZT0, WHITE ON)
LIGHT_OFF_TIME = dtime(19, 0)   # 7:00 PM (IR ON)

LED_ON  = GPIO.LOW   # Active-LOW relay
LED_OFF = GPIO.HIGH

# ============================================
# CAMERA SETUP
# ============================================

cam = Camera()
cam.resolution = (1920, 1080)

# ============================================
# GPIO SETUP (SAFE)
# ============================================

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(WHITE_LED_PIN, GPIO.OUT, initial=LED_OFF)
GPIO.setup(IR_LED_PIN, GPIO.OUT, initial=LED_OFF)

def force_light_state(is_daytime: bool):
    """
    Guarantees:
    - Exactly one LED ON
    - Supports active-LOW hardware
    """
    if is_daytime:
        GPIO.output(IR_LED_PIN, LED_OFF)
        GPIO.output(WHITE_LED_PIN, LED_ON)
    else:
        GPIO.output(WHITE_LED_PIN, LED_OFF)
        GPIO.output(IR_LED_PIN, LED_ON)

# ============================================
# DIRECTORY + LOGGING
# ============================================

os.makedirs(SAVE_DIR, exist_ok=True)

log_filename = os.path.join(SAVE_DIR, f"{EXPERIMENT_ID}_experiment.log")
csv_filename = os.path.join(SAVE_DIR, f"{EXPERIMENT_ID}_frames.csv")

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

if not os.path.exists(csv_filename):
    with open(csv_filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "experiment_id",
            "frame_number",
            "exp_day",
            "zt_frame",
            "light_state",
            "filename"
        ])

# ============================================
# TIME HELPERS
# ============================================

def is_daytime_clock(now):
    """Clock-based light control (7AM–7PM = DAY)."""
    return LIGHT_ON_TIME <= now.time() < LIGHT_OFF_TIME

# ============================================
# IMAGE CAPTURE
# ============================================

def capture_image(now, frame_number, exp_day, zt_frame, light_state):

    timestamp = now.strftime("%Y%m%d_%H%M%S")

    base_name = (
        f"{EXPERIMENT_ID}_Frame{frame_number:03d}_"
        f"Day{exp_day:02d}_ZT{zt_frame:03d}_{timestamp}"
    )

    jpg_path = os.path.join(SAVE_DIR, base_name + ".jpg")
    tiff_path = os.path.join(SAVE_DIR, base_name + ".tiff")

    cam.capture_image(jpg_path)

    with Image.open(jpg_path) as img:
        img.save(tiff_path, format="TIFF")

    os.remove(jpg_path)

    with open(csv_filename, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            EXPERIMENT_ID,
            frame_number,
            exp_day,
            zt_frame,
            "DAY" if light_state else "NIGHT",
            os.path.basename(tiff_path)
        ])

    logging.info(
        f"Frame {frame_number} | "
        f"Day {exp_day} | "
        f"ZT{zt_frame:03d} | "
        f"{'DAY' if light_state else 'NIGHT'}"
    )

    print(f"Saved {base_name}")

# ============================================
# MAIN EXPERIMENT LOOP
# ============================================

def run_experiment():

    now = datetime.now()

    # =====================================
    # ALIGN EXPERIMENT START TO NEXT 7:00 AM
    # =====================================
    today_zt0 = datetime.combine(now.date(), LIGHT_ON_TIME)

    if now < today_zt0:
        experiment_start = today_zt0
    else:
        experiment_start = today_zt0 + timedelta(days=1)

    logging.info(f"Script started at {now}")
    logging.info(f"Experiment scheduled to start at {experiment_start}")

    print(f"Current time: {now}")
    print(f"Experiment will start at: {experiment_start}")

    # =====================================
    # WAIT UNTIL 7:00 AM (ZT0)
    # =====================================
    while datetime.now() < experiment_start:

        now = datetime.now()
        desired_state = is_daytime_clock(now)
        force_light_state(desired_state)

        time.sleep(1)

    logging.info("ZT0 reached. Beginning image capture.")
    print("ZT0 reached. Beginning image capture.")

    # =====================================
    # PRE-CALCULATE TOTAL FRAMES (216)
    # =====================================
    total_frames = int((TOTAL_HOURS * 3600) / CAPTURE_INTERVAL_SEC)
    print(f"Total frames scheduled: {total_frames}")

    current_light_state = True  # At 7AM, lights are DAY
    force_light_state(True)

    # =====================================
    # MAIN CAPTURE LOOP (ZT0 → ZT215)
    # =====================================
    for frame_number in range(total_frames):  # 0 → 215

        scheduled_time = experiment_start + timedelta(
            seconds=frame_number * CAPTURE_INTERVAL_SEC
        )

        while datetime.now() < scheduled_time:

            now = datetime.now()
            desired_state = is_daytime_clock(now)

            if desired_state != current_light_state:
                force_light_state(desired_state)
                current_light_state = desired_state
                logging.info(
                    f"Light transition → "
                    f"{'DAY (WHITE)' if desired_state else 'NIGHT (IR)'}"
                )

            time.sleep(0.5)

        now = datetime.now()

        zt_frame = frame_number  # ZT0–ZT215

        exp_elapsed_sec = (now - experiment_start).total_seconds()
        exp_day = int(exp_elapsed_sec // (24 * 3600))

        capture_image(
            now=now,
            frame_number=frame_number,
            exp_day=exp_day,
            zt_frame=zt_frame,
            light_state=current_light_state
        )

        print(f"ZT{frame_number:03d} complete")

    logging.info("Experiment complete.")
    print("Experiment complete.")

# ============================================
# RUN + CLEANUP
# ============================================

try:
    run_experiment()

except KeyboardInterrupt:
    print("Experiment interrupted.")

finally:
    GPIO.output(WHITE_LED_PIN, LED_OFF)
    GPIO.output(IR_LED_PIN, LED_OFF)
    GPIO.cleanup()

    try:
        cam.stop()
    except:
        pass

    print("Experiment finished cleanly.")
