import os

APP_ID = "com.ecriv1.voicetotext"

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(BASE_DIR, "icons")
ICON_MIC_OFF = "mic-off"
ICON_MIC_ON = "mic-on"

# Audio
SAMPLE_RATE = 16000
BLOCK_SIZE = 8000
AUDIO_DEVICE = None  # None = system default microphone

# Hotkey
HOTKEY = "<f4>"

# Text injection
TYPING_DELAY_MS = 12
USE_CLIPBOARD_INJECTION = False  # use xdotool type (more reliable)
