"""Run the TertulIA FastAPI server. Execute from the project root: python run_api.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("tertulia.api.main:app", host="0.0.0.0", port=8000, reload=True)
