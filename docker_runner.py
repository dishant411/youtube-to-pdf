#!/usr/bin/env python3
"""Build and run this project through Docker.

Examples:
    python3 docker_runner.py 'https://youtu.be/dQw4w9WgXcQ'
    python3 docker_runner.py examples/urls.txt
    python3 docker_runner.py --rebuild 'https://youtu.be/dQw4w9WgXcQ'
"""

from __future__ import annotations

import sys

from run_converter import main


if __name__ == "__main__":
    sys.exit(main())
