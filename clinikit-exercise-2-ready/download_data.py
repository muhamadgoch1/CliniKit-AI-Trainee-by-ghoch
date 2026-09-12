"""Download the dataset. Kaggle authentication may be required."""
from pathlib import Path
import shutil,kagglehub
src=Path(kagglehub.dataset_download("joniarroba/noshowappointments")); files=list(src.glob("*.csv"))
if not files: raise FileNotFoundError(f"No CSV in {src}")
dest=Path("data/noshowappointments.csv"); dest.parent.mkdir(exist_ok=True); shutil.copy2(files[0],dest); print(dest)
