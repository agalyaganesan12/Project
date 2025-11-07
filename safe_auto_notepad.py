# safe_auto_notepad.py
import time
import os
import datetime
import pyautogui

# --- SAFETY / COMFORT SETTINGS ---
pyautogui.FAILSAFE = True          # move mouse to top-left to abort
pyautogui.PAUSE = 0.05             # tiny pause after each action

def open_notepad():
    # Win+R -> "notepad" -> Enter
    pyautogui.hotkey('win', 'r')
    time.sleep(0.6)
    pyautogui.write('notepad')
    pyautogui.press('enter')
    # give Notepad time to appear and focus
    time.sleep(1.2)

def type_form():
    pyautogui.write("Name: Agalya", interval=0.05)
    pyautogui.press('enter')
    pyautogui.write("Address: 123, Chennai, Tamil Nadu", interval=0.05)
    pyautogui.press('enter')
    pyautogui.write("Email: agalya@example.com", interval=0.05)
    pyautogui.press('enter')
    pyautogui.press('enter')
    pyautogui.write("Thank you!", interval=0.05)
    pyautogui.press('enter')
    pyautogui.write("This file was created automatically by PyAutoGUI.", interval=0.05)

def save_file_to_desktop():
    # Build a unique Desktop path like: C:\Users\<you>\Desktop\auto_form-2025-11-07_21-34-12.txt
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"auto_form-{ts}.txt"
    fullpath = os.path.join(desktop, filename)

    # Ctrl+S -> Save As dialog -> type full path -> Enter
    time.sleep(0.6)
    pyautogui.hotkey('ctrl', 's')
    time.sleep(0.8)
    pyautogui.write(fullpath, interval=0.01)
    pyautogui.press('enter')

    # give Windows a moment to save
    time.sleep(0.8)
    return fullpath

if __name__ == "__main__":
    print("Starting in 3 seconds... (bring any other windows out of the way)")
    time.sleep(3)

    open_notepad()
    type_form()
    saved_path = save_file_to_desktop()
    print(f"✅ Form filled and saved to:\n{saved_path}\n")
    print("Tip: Press Ctrl+C in the terminal or move your mouse to the top-left corner to abort mid-run.")
