
import os
import streamlit as st


def get_setting(name, default=None):
    """Read a setting from environment variables or Streamlit Secrets."""

    value = os.getenv(name)

    if value:
        return value

    try:
        return st.secrets.get(name, default)
    except Exception:
        # Streamlit Secrets may not be configured during local development.
        return default
