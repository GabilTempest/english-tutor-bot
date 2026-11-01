import sys
import time
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON_EXE = BASE_DIR / "venv" / "Scripts" / "python.exe"
BOT_PY = BASE_DIR / "bot.py"
LOG_FILE = BASE_DIR / "bot_supervisor.log"

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [Supervisor] {msg}\n"
    print(line, end="")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

def main():
    log("==================================================")
    log("English Tutor Bot Watchdog Supervisor Started")
    log("Monitoring bot.py for 24/7 continuous operation...")
    log("==================================================")
    
    restart_count = 0
    while True:
        try:
            start_time = time.time()
            log(f"Starting bot.py (run attempt #{restart_count + 1})...")
            
            # Run bot process
            p = subprocess.Popen([str(PYTHON_EXE), str(BOT_PY)], cwd=str(BASE_DIR))
            p.wait()
            exit_code = p.returncode
            run_duration = time.time() - start_time
            log(f"bot.py exited with return code {exit_code} (uptime: {run_duration:.1f}s)")
            
            # If manually stopped with Ctrl+C or exited immediately with 0
            if exit_code == 0 and run_duration < 3:
                log("Clean exit detected within 3 seconds. Watchdog stopping.")
                break
            
            restart_count += 1
            log("Restarting bot.py in 5 seconds...")
            time.sleep(5)
            
        except KeyboardInterrupt:
            log("Watchdog supervisor stopped by user (KeyboardInterrupt).")
            break
        except Exception as e:
            log(f"Watchdog supervisor error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
