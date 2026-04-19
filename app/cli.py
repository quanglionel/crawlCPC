from __future__ import annotations

import sys

from app.main import main


if __name__ == "__main__":
    main(["crawl", *sys.argv[1:]])
