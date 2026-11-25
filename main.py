"""Vercel entry point: seed an isolated, read-only synthetic demo."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

# Each function process builds its own snapshot in writable temporary storage.
_snapshot = TemporaryDirectory(prefix="payment-trust-lab-")
os.environ["FRAUD_LAB_DB"] = str(Path(_snapshot.name) / "demo.sqlite3")
os.environ["READ_ONLY_DEMO"] = "1"

from app.seed import seed
from app.main import app

seed()
