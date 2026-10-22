"""Load the deterministic, Node-generated Streamlit visual theme."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st

_THEME_PATH = Path(__file__).with_name("theme.css")


@lru_cache(maxsize=1)
def load_theme_css() -> str:
    """Return the repository-owned static stylesheet."""

    return _THEME_PATH.read_text(encoding="utf-8")


def apply_theme() -> None:
    """Inject only the trusted static stylesheet into the Streamlit page."""

    st.markdown(f"<style>{load_theme_css()}</style>", unsafe_allow_html=True)
