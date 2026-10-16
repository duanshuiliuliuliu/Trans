"""Trans —— 极简划词翻译托盘工具。"""

import os
import sys

__version__ = "0.1.0"

APP_NAME = "Trans"


def resource_dir() -> str:
    """资源目录：源码运行时为仓库根目录，PyInstaller 打包后为解包目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
