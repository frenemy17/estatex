import sys
from pathlib import Path

# Add backend directory to python path
sys.path.append(str(Path(__file__).parent.parent / "backend"))

from server import app
