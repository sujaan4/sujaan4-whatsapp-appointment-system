from __future__ import annotations

import os
import sys

from streamlit.web import cli as stcli


def main() -> int:
    port = os.getenv("PORT", "8501")
    sys.argv = [
        "streamlit",
        "run",
        "dashboard.py",
        "--server.headless=true",
        "--server.address=0.0.0.0",
        f"--server.port={port}",
    ]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
