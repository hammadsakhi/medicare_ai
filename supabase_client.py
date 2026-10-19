
import os

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client
from config import get_setting

load_dotenv()


def get_supabase_client() -> Client:
    """Return a Supabase client isolated to this Streamlit session."""

    if "_supabase_client" not in st.session_state:
        supabase_url = get_setting("SUPABASE_URL")
        supabase_key = get_setting("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            raise RuntimeError(
                "Supabase configuration is missing. "
                "Check SUPABASE_URL and SUPABASE_KEY in your .env file."
            )

        st.session_state["_supabase_client"] = create_client(
            supabase_url,
            supabase_key,
        )

    return st.session_state["_supabase_client"]
