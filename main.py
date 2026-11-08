"""Entry point for hosting (Railway): runs the Discord bot straight from src/
without needing the package installed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from deadlock_bot.bot import main

if __name__ == "__main__":
    main()
