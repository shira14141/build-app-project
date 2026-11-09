"""מפעיל את השרת ואת הממשק יחד בפקודה אחת:  python run_dev.py

- שרת API:  http://127.0.0.1:8000   (תיעוד: /docs)
- ממשק:     http://localhost:8501   (נפתח אוטומטית בדפדפן)
Ctrl+C עוצר את שניהם.
"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def wait_for_api(url="http://127.0.0.1:8000/health", timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as res:
                if res.status == 200:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", "8000", "--reload"], cwd=ROOT)
    if not wait_for_api():
        print("The API server did not start - see the error above.")
        api.terminate()
        return 1
    ui = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "frontend.py"], cwd=ROOT)
    try:
        while api.poll() is None and ui.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (ui, api):
            if proc.poll() is None:
                proc.terminate()
        for proc in (ui, api):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
