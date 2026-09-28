#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bci_tcp_server.py (Root Wrapper)
--------------------------------
프로젝트 루트에서 'python bci_tcp_server.py'를 실행할 때,
unity/connect/bci_online_server.py 를 자동으로 호출해주는 표준 진입점입니다.
"""

import os
import sys
from pathlib import Path

# unity/connect 경로를 sys.path에 추가
connect_dir = Path(__file__).resolve().parent / "unity" / "connect"
if str(connect_dir) not in sys.path:
    sys.path.insert(0, str(connect_dir))

from bci_online_server import main

if __name__ == "__main__":
    main()
