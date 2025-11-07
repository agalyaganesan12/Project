import time
import pyautogui

pyautogui.FAILSAFE = True

GROUP_NAME = "SE - AI-B3 - 2"
MESSAGE = (
    "Hello everyone! One week Completed! This is an automated message sent via PyAutoGUI.\n"
    "Have a nice day!"
)

# === TUNE THESE IF NEEDED ===
MAX_ALT_TAB_CYCLES = 20
DELAY = 1.0
CONF = 0.65           # lower confidence helps if your template is good
WA_IMAGE = "whatsapp_indicator.png"   # small, unique piece of WhatsApp UI (see notes)

time.sleep(3)

def whatsapp_visible():
    try:
        # grayscale=True makes matching more tolerant (light/dark mode)
        return pyautogui.locateOnScreen(WA_IMAGE, confidence=CONF, grayscale=True) is not None
    except pyautogui.ImageNotFoundException:
        return False

print("Searching for WhatsApp window...")
for _ in range(MAX_ALT_TAB_CYCLES):
    if whatsapp_visible():
        print("✅ WhatsApp window detected")
        break
    # alt+tab to next window
    pyautogui.keyDown('alt')
    pyautogui.press('tab')
    pyautogui.keyUp('alt')
    time.sleep(DELAY)
else:
    raise SystemExit("❌ WhatsApp window not found. Recheck the template image & see tips below.")

# Ensure Chrome has focus and WA page is active
time.sleep(0.8)
screen_w, screen_h = pyautogui.size()
pyautogui.click(screen_w // 2, screen_h // 2)
time.sleep(0.4)

# Reset zoom to 100% (matching the template scale)
pyautogui.hotkey('ctrl', '0')
time.sleep(0.4)

# Use WhatsApp search to locate the group by NAME (no image file needed)
pyautogui.hotkey('ctrl', 'f')   # or try 'ctrl', 'k' if your WA layout differs
time.sleep(0.5)
pyautogui.write(GROUP_NAME, interval=0.03)
time.sleep(1.0)
pyautogui.press('enter')
time.sleep(0.8)

# Focus message box and send
pyautogui.click(screen_w // 2, screen_h - 120)  # generic click near chat input
time.sleep(0.3)
pyautogui.write(MESSAGE, interval=0.03)
pyautogui.press('enter')

print("✅ Message sent.")
