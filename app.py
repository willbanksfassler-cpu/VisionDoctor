"""Streamlit entry point for the VisionDoctor MVP."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from vision_doctor.ui import render_app


def main() -> None:
    """Configure and render the single-page application."""

    import streamlit as st

    st.set_page_config(
        page_title="VisionDoctor 数据集体检",
        page_icon="🩺",
        layout="wide",
    )
    try:
        render_app()
    except Exception:  # noqa: BLE001 - final UI trust boundary
        st.error(
            "页面暂时无法正常显示，请清除当前上传文件后重试。"
        )


if __name__ == "__main__":
    main()
