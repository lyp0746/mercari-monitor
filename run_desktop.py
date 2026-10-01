"""
Desktop App Launcher
Usage: uv run python run_desktop.py
"""

import subprocess
import sys
import os

def main():
    print("=" * 50)
    print("  Starting Desktop Application...")
    print("=" * 50)
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        subprocess.run([sys.executable, "src/main.py"], check=True)
    except KeyboardInterrupt:
        print("\n[INFO] Application stopped")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()