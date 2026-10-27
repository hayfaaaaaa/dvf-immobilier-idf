"""Lance tout le pipeline : python run_all.py  (ou python run_all.py --skip-download)"""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
STEPS = ["01_download.py", "02_clean.py", "03_build_db.py", "04_sql_analysis.py", "05_model.py"]

if __name__ == "__main__":
    steps = STEPS[1:] if "--skip-download" in sys.argv else STEPS
    for s in steps:
        print(f"\n{'=' * 70}\n>>> {s}\n{'=' * 70}")
        subprocess.run([sys.executable, str(SRC / s)], check=True)
    print("\nPipeline terminé.")
