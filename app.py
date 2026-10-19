
import json
import os
import re
from datetime import date, datetime
from html import escape

import streamlit as st
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from streamlit_cookies_controller import CookieController

from auth_service import (
    register_user,
    login_user,
    logout_user,
    restore_login,
)
from config import get_setting
from database import init_db
from tools import (
    TOOL_LIST,
    execute_tool,
    list_doctors,
    find_appointment,
    cancel_appointment,
)


# =========================================================
# 1. CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="MediCare AI | Appointment Assistant",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_dotenv()

COOKIE_NAME = "medicare_session"
SESSION_MAX_AGE = 7 * 24 * 60 * 60


# =========================================================
# 2. DATABASE INITIALIZATION
# =========================================================

@st.cache_resource
def setup_database():
    init_db()
    return True


try:
    setup_database()
except Exception as error:
    st.error(
        "Unable to initialize PostgreSQL. "
        "Check DATABASE_URL and your database configuration."
    )
    with st.expander("Technical details"):
        st.code(str(error))
    st.stop()


# =========================================================
# 3. COOKIE INITIALIZATION AND LOGIN RESTORATION
# =========================================================

cookie_controller = CookieController(
    key="medicare_cookie_controller"
)

if not st.session_state.get("authenticated_user"):
    cookies = cookie_controller.getAll()

    # Wait for the browser cookie component to initialize.
    if cookies is None:
        st.info("Loading your saved session...")
        st.stop()

    saved_token = (
        cookies.get(COOKIE_NAME)
        if isinstance(cookies, dict)
        else None
    )

    if saved_token:
        try:
            restored = restore_login(saved_token)

            if not restored:
                try:
                    cookie_controller.remove(COOKIE_NAME)
                except Exception as cookie_error:
                    print(f"Cookie removal error: {cookie_error}")

                st.warning(
                    "Your saved session is no longer valid. "
                    "Please log in again."
                )

        except Exception as error:
            print(f"Session restoration error: {error}")
            st.error(
                "Unable to restore your saved session. "
                "Please try logging in again."
            )


# =========================================================
# 4. STYLING
# =========================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"], .stApp {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp, [data-testid="stAppViewContainer"] {
        background: #f4f7fb;
        color: #1e293b;
    }

    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    [data-testid="stAppViewContainer"] h3,
    [data-testid="stAppViewContainer"] h4,
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] li,
    [data-testid="stAppViewContainer"] label {
        color: #1e293b;
    }

    [data-testid="stSidebar"] {
        background: #102a43;
    }

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] li {
        color: #f2f7ff !important;
    }

    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: #cbd9e8 !important;
    }

    .hero {
        background: linear-gradient(120deg, #123c69, #087f8c);
        padding: 30px;
        border-radius: 20px;
        margin-bottom: 24px;
        box-shadow: 0 8px 24px rgba(18, 60, 105, 0.12);
    }

    .hero h1 {
        color: white !important;
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .hero p {
        color: #e1f4f6 !important;
        margin-bottom: 0;
    }

    .info-card {
        background: white;
        padding: 20px;
        min-height: 90px;
        border-radius: 16px;
        border: 1px solid #e2eaf2;
        margin-bottom: 12px;
        color: #20354a !important;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
    }

    .info-card b {
        color: #123c69 !important;
    }

    [data-testid="stChatMessage"] {
        background: white !important;
        border: 1px solid #e2eaf2;
        border-radius: 16px;
        padding: 14px;
        margin-bottom: 10px;
    }

    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li,
    [data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {
        color: #1e293b !important;
    }

    [data-testid="stChatMessage"] table {
        width: 100%;
        border-collapse: collapse;
        background: white !important;
        color: #1e293b !important;
    }

    [data-testid="stChatMessage"] th,
    [data-testid="stChatMessage"] td {
        color: #1e293b !important;
        background: white !important;
        border: 1px solid #dbe5ef !important;
        padding: 10px !important;
        text-align: left;
    }

    [data-testid="stChatMessage"] th {
        background: #e8f3f7 !important;
        color: #123c69 !important;
    }

    [data-testid="stChatInput"] {
        background: white !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 14px !important;
    }

    [data-testid="stChatInput"] textarea {
        color: #1e293b !important;
        background: white !important;
        -webkit-text-fill-color: #1e293b !important;
        caret-color: #087f8c !important;
    }

    [data-testid="stChatInput"] textarea::placeholder {
        color: #64748b !important;
        -webkit-text-fill-color: #64748b !important;
    }

    .stButton button {
        background: #087f8c;
        color: white !important;
        border: none;
        border-radius: 10px;
    }

    .stButton button p,
    .stButton button span {
        color: white !important;
    }

    .stButton button:hover {
        background: #066874;
    }

    [data-testid="stAppViewContainer"] hr {
        border-color: #dbe5ef;
    }

    @media (max-width: 768px) {
        .hero {
            padding: 22px;
        }

        .hero h1 {
            font-size: 25px;
        }

        .info-card {
            padding: 14px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 5. LOGIN AND REGISTRATION
# =========================================================

if not st.session_state.get("authenticated_user"):

    st.markdown(
        """
        <div class="hero">
            <h1>🏥 MediCare AI</h1>
            <p>Your assistant for doctor discovery and appointment scheduling.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Welcome")
    st.write(
        "Log in or create an account to access your appointment assistant."
    )

    login_tab, register_tab = st.tabs(
        ["Log in", "Create account"]
    )

    with login_tab:
        with st.form("login_form"):
            login_email = st.text_input(
                "Email address",
                key="login_email",
            )
            login_password = st.text_input(
                "Password",
                type="password",
                key="login_password",
            )
            login_submitted = st.form_submit_button(
                "Log in",
                use_container_width=True,
            )

        if login_submitted:
            try:
                result = login_user(
                    login_email,
                    login_password,
                )

                if not result.get("success"):
                    st.error(
                        result.get("message", "Unable to log in.")
                    )

                else:
                    token = result.get("session_token")
                    user = result.get("user")

                    if not token or not user:
                        st.error(
                            "Login succeeded, but no saved session was returned."
                        )

                    else:
                        try:
                            cookie_controller.set(
                                COOKIE_NAME,
                                token,
                                max_age=SESSION_MAX_AGE,
                            )

                            st.session_state["authenticated_user"] = user
                            st.session_state["session_token"] = token
                            st.session_state["cookie_checked"] = True

                            st.success("Login successful.")
                            st.rerun()

                        except Exception as error:
                            print(f"Cookie save error: {error}")

                            try:
                                logout_user(token)
                            except Exception as logout_error:
                                print(
                                    "Session cleanup error: "
                                    f"{logout_error}"
                                )

                            st.error(
                                "Could not save your login in the browser. "
                                "Please try again."
                            )

            except Exception as error:
                print(f"Login error: {error}")
                st.error(
                    "Login could not be completed. Please try again."
                )

    with register_tab:
        with st.form("register_form"):
            register_name = st.text_input(
                "Full name",
                key="register_name",
            )
            register_email = st.text_input(
                "Email address",
                key="register_email",
            )
            register_password = st.text_input(
                "Create password",
                type="password",
                key="register_password",
            )
            register_confirm = st.text_input(
                "Confirm password",
                type="password",
                key="register_confirm",
            )
            register_submitted = st.form_submit_button(
                "Create account",
                use_container_width=True,
            )

        if register_submitted:
            try:
                result = register_user(
                    register_name,
                    register_email,
                    register_password,
                    register_confirm,
                )

                if result.get("success"):
                    st.success(
                        result.get("message", "Account created.")
                    )

                    if result.get("verified"):
                        st.info("You can now log in.")
                else:
                    st.error(
                        result.get(
                            "message",
                            "Unable to create account.",
                        )
                    )

            except Exception as error:
                print(f"Registration error: {error}")
                st.error(
                    "Registration could not be completed. Please try again."
                )

    st.caption(
        "Portfolio demonstration using fictional doctors. "
        "Do not enter sensitive medical information."
    )

    if not st.session_state.get("authenticated_user"):
        st.stop()


# =========================================================
# 6. AUTHENTICATED USER
# =========================================================

current_user = st.session_state.get("authenticated_user")

if not isinstance(current_user, dict) or not current_user.get("id"):
    st.session_state.pop("authenticated_user", None)
    st.session_state.pop("session_token", None)
    st.rerun()

supabase_user_id = current_user["id"]


# =========================================================
# 7. GROQ MODEL
# =========================================================

api_key = get_setting("GROQ_API_KEY")
model_name = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile",
)

if not api_key or api_key == "your_groq_api_key_here":
    st.error("Please configure GROQ_API_KEY in your .env file.")
    st.stop()


@st.cache_resource
def get_ai_model(key, model):
    return ChatGroq(
        model=model,
        api_key=key,
        temperature=0,
    ).bind_tools(TOOL_LIST)


llm = get_ai_model(api_key, model_name)


# =========================================================
# 8. CHAT SESSION STATE
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hello! Welcome to **MediCare AI**. 🏥\n\n"
                "I can help you find doctors, check availability, "
                "book appointments, find your bookings, and cancel "
                "appointments.\n\nHow can I help you today?"
            ),
        }
    ]

if "cancel_flow" not in st.session_state:
    st.session_state.cancel_flow = None


def add_message(role, content):
    """Save a message and display it."""
    st.session_state.messages.append(
        {"role": role, "content": content}
    )

    with st.chat_message(role):
        st.markdown(content)


def normalize_confirmation(value):
    """Normalize confirmation text for comparison."""
    return re.sub(
        r"[^a-z0-9 ]",
        "",
        value.lower(),
    ).strip()


def is_booking_tool(tool_name):
    """Identify the appointment-booking tool by its name."""
    normalized = re.sub(
        r"[^a-z0-9]",
        "",
        str(tool_name).lower(),
    )

    return normalized in {
        "bookappointment",
        "bookappointmenttool",
        "createappointment",
    }


def get_result_value(result, *keys, default="Not provided"):
    """Return the first available non-empty field from a tool result."""
    for key in keys:
        value = result.get(key)

        if value is not None and str(value).strip():
            return value

    appointment = result.get("appointment")

    if isinstance(appointment, dict):
        for key in keys:
            value = appointment.get(key)

            if value is not None and str(value).strip():
                return value

    return default


def authoritative_date_display(result):
    """
    Prefer the date display returned by the booking tool.
    If absent, calculate the weekday using Python, not the AI model.
    """
    display = get_result_value(
        result,
        "date_display",
        "formatted_date",
        default="",
    )

    if display:
        return str(display)

    raw_date = get_result_value(
        result,
        "date",
        "appointment_date",
        "requested_date",
        default="",
    )

    if isinstance(raw_date, datetime):
        raw_date = raw_date.date()

    if isinstance(raw_date, date):
        parsed_date = raw_date
    else:
        try:
            parsed_date = date.fromisoformat(
                str(raw_date).strip()[:10]
            )
        except (ValueError, TypeError):
            return str(raw_date or "Not provided")

    return parsed_date.strftime("%d %B %Y (%A)")


def format_booking_success(result):
    """Create a deterministic confirmation from the actual tool result."""
    booking_id = get_result_value(
        result,
        "appointment_id",
        "booking_id",
        "id",
    )
    patient_name = get_result_value(
        result,
        "patient_name",
        "name",
    )
    doctor_name = get_result_value(
        result,
        "doctor",
        "doctor_name",
    )
    date_display = authoritative_date_display(result)
    appointment_time = get_result_value(
        result,
        "time",
        "appointment_time",
    )

    return (
        "✅ **Appointment booked successfully!**\n\n"
        "Your booking was saved by the appointment system.\n\n"
        f"- **Booking ID:** {booking_id}\n"
        f"- **Patient:** {patient_name}\n"
        f"- **Doctor:** {doctor_name}\n"
        f"- **Date:** {date_display}\n"
        f"- **Time:** {appointment_time}\n"
        "- **Status:** Confirmed\n\n"
        "Please keep your booking ID for future lookup or cancellation."
    )


def format_booking_failure(result):
    """Report a booking failure without claiming success."""
    message = result.get(
        "message",
        "The appointment system could not complete the booking.",
    )

    return (
        "⚠️ **The appointment was not confirmed.**\n\n"
        f"{message}\n\n"
        "Please check the details or choose another available slot."
    )


# =========================================================
# 9. SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("# 🏥 MediCare AI")
    st.caption("Medical Center Assistant")
    st.divider()

    st.markdown("### Account")
    st.markdown(
        f"**{escape(str(current_user.get('name', 'Patient')))}**"
    )
    st.caption(str(current_user.get("email", "")))

    if st.button("Log out", use_container_width=True):
        token = st.session_state.get("session_token")

        try:
            logout_user(token)
        except Exception as error:
            print(f"Logout error: {error}")
            st.error(
                "The server session could not be revoked. "
                "Please try again."
            )
            st.stop()

        try:
            cookie_controller.remove(COOKIE_NAME)
        except Exception as error:
            print(f"Cookie removal error: {error}")

        for key in (
            "authenticated_user",
            "session_token",
            "messages",
            "cancel_flow",
            "cookie_checked",
        ):
            st.session_state.pop(key, None)

        st.rerun()

    st.divider()
    st.markdown("### Services")
    st.markdown(
        """
        - 🩺 Find a doctor
        - 📅 Check availability
        - 📝 Book an appointment
        - 🔎 Find a booking
        - ❌ Cancel an appointment
        """
    )

    st.divider()
    st.markdown("### Doctor Directory")

    try:
        directory = list_doctors.invoke({"specialty": ""})

        if directory.get("doctors"):
            for doctor in directory["doctors"]:
                st.markdown(f"**{doctor['name']}**")
                st.caption(doctor["specialty"])
                st.markdown(
                    f"`{doctor['doctor_id']}` · "
                    f"{doctor['working_days']}"
                )
                st.caption(
                    f"{doctor['start_time']} – {doctor['end_time']}"
                )
                st.divider()
        else:
            st.info("No doctors have been added yet.")

    except Exception as error:
        print(f"Doctor directory error: {error}")
        st.warning("The doctor directory is unavailable.")

    if st.button("＋ Start New Chat", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Hello! Welcome to MediCare AI. "
                    "How can I help with appointments today?"
                ),
            }
        ]
        st.session_state.cancel_flow = None
        st.rerun()

    st.caption("Portfolio demo · Fictional doctors")


# =========================================================
# 10. MAIN PAGE
# =========================================================

st.markdown(
    """
    <div class="hero">
        <h1>Care starts with a conversation.</h1>
        <p>Your assistant for doctor discovery and appointment scheduling.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        """
        <div class="info-card">
            🩺 <b>Find Doctors</b><br>
            Explore specialties and clinic hours.
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
        <div class="info-card">
            📅 <b>Check Availability</b><br>
            Find open appointment slots by date.
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        """
        <div class="info-card">
            🔐 <b>Manage Bookings</b><br>
            Manage your own appointments.
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("### Chat with MediCare AI")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# =========================================================
# 11. CHAT INPUT
# =========================================================

user_text = st.chat_input("Type your message here...")


# =========================================================
# 12. CANCELLATION WORKFLOW
# =========================================================

if user_text:
    add_message("user", user_text)
    normalized_text = normalize_confirmation(user_text)

    if (
        st.session_state.cancel_flow is not None
        and normalized_text == "cancel request"
    ):
        st.session_state.cancel_flow = None
        add_message(
            "assistant",
            "Cancellation request stopped. "
            "Your appointment has not been cancelled.",
        )
        st.stop()

    flow = st.session_state.cancel_flow

    if flow is not None:
        stage = flow.get("stage")

        if stage == "need_id":
            match = re.fullmatch(r"\s*(\d+)\s*", user_text)

            if not match:
                add_message(
                    "assistant",
                    "Please enter the numeric appointment ID "
                    "shown on your booking confirmation.",
                )
            else:
                flow["appointment_id"] = int(match.group(1))
                flow["stage"] = "need_phone"

                add_message(
                    "assistant",
                    "Now enter the phone number used when "
                    "booking the appointment.",
                )

        elif stage == "need_phone":
            patient_phone = user_text.strip()

            try:
                result = find_appointment.invoke(
                    {
                        "appointment_id": flow["appointment_id"],
                        "patient_phone": patient_phone,
                        "supabase_user_id": supabase_user_id,
                    }
                )

                if not result.get("found"):
                    add_message(
                        "assistant",
                        "I couldn't find an appointment matching "
                        "those details in your account. Check the "
                        "booking ID and phone number, then try again. "
                        "Type CANCEL REQUEST to stop.",
                    )
                else:
                    appointment = result["appointment"]

                    if appointment["status"] != "confirmed":
                        st.session_state.cancel_flow = None

                        add_message(
                            "assistant",
                            f"This appointment is already "
                            f"**{appointment['status']}** and cannot "
                            "be cancelled again.",
                        )
                    else:
                        flow["patient_phone"] = patient_phone
                        flow["appointment_details"] = appointment
                        flow["stage"] = "awaiting_confirmation"

                        appointment_date = (
                            appointment.get("date_display")
                            or appointment.get("date", "Not provided")
                        )

                        add_message(
                            "assistant",
                            (
                                "Please review your appointment:\n\n"
                                f"- **Booking ID:** "
                                f"{appointment['appointment_id']}\n"
                                f"- **Patient:** "
                                f"{appointment['patient_name']}\n"
                                f"- **Doctor:** {appointment['doctor']}\n"
                                f"- **Date:** {appointment_date}\n"
                                f"- **Time:** {appointment['time']}\n"
                                f"- **Status:** {appointment['status']}\n\n"
                                "To proceed, type **CONFIRM CANCEL**. "
                                "To keep your appointment, type **NO**."
                            ),
                        )

            except Exception as error:
                print(f"Appointment lookup error: {error}")
                add_message(
                    "assistant",
                    "I couldn't verify that booking right now. "
                    "Please try again.",
                )

        elif stage == "awaiting_confirmation":
            if normalized_text == "confirm cancel":
                try:
                    result = cancel_appointment.invoke(
                        {
                            "appointment_id": flow["appointment_id"],
                            "patient_phone": flow["patient_phone"],
                            "supabase_user_id": supabase_user_id,
                        }
                    )

                    if result.get("success") is True:
                        details = flow["appointment_details"]
                        appointment_date = (
                            details.get("date_display")
                            or details.get("date", "Not provided")
                        )

                        add_message(
                            "assistant",
                            (
                                "✅ **Appointment cancelled successfully.**\n\n"
                                f"- **Booking ID:** "
                                f"{details['appointment_id']}\n"
                                f"- **Doctor:** {details['doctor']}\n"
                                f"- **Date:** {appointment_date}\n"
                                f"- **Time:** {details['time']}\n\n"
                                "The cancellation has been saved to the database."
                            ),
                        )
                    else:
                        add_message(
                            "assistant",
                            result.get(
                                "message",
                                "The appointment could not be cancelled.",
                            ),
                        )

                except Exception as error:
                    print(f"Appointment cancellation error: {error}")
                    add_message(
                        "assistant",
                        "The cancellation could not be completed. "
                        "Please try again.",
                    )

                finally:
                    st.session_state.cancel_flow = None

            elif normalized_text in {
                "no",
                "no cancel",
                "keep appointment",
            }:
                st.session_state.cancel_flow = None
                add_message(
                    "assistant",
                    "Cancellation stopped. Your appointment "
                    "has not been cancelled.",
                )

            else:
                add_message(
                    "assistant",
                    "Type **CONFIRM CANCEL** to proceed or "
                    "**NO** to keep your appointment.",
                )

        st.stop()

    lower_text = user_text.lower()

    cancellation_intent = (
        bool(re.search(r"\b(cancel|cancellation)\b", lower_text))
        and any(
            word in lower_text
            for word in (
                "appointment",
                "booking",
                "reservation",
                "my",
                "it",
            )
        )
    ) or normalized_text in {
        "cancel",
        "cancel appointment",
        "cancel my appointment",
        "i want to cancel",
    }

    if cancellation_intent:
        st.session_state.cancel_flow = {"stage": "need_id"}

        add_message(
            "assistant",
            "I can help cancel an appointment belonging to "
            "your account. First, enter its numeric booking ID.",
        )
        st.stop()

    # =====================================================
    # 13. NORMAL AI CONVERSATION
    # =====================================================

    system_prompt = SystemMessage(
        content="""
You are MediCare AI, a professional appointment assistant.

GENERAL RULES
- Use tools for doctor details, clinic schedules, availability,
  and appointment records.
- Never invent doctor information, available slots, booking IDs,
  appointment records, or operation results.
- Never diagnose conditions or recommend treatment.
- For emergencies, advise contacting local emergency services.
- Keep responses friendly, concise, and professional.

BOOKING RULES
1. Before booking, collect the patient's name, phone, doctor,
   date, time, and optional reason.
2. Check availability using the database before proposing a slot.
3. Show the proposed details and ask for explicit confirmation.
4. Only call the booking tool after the patient explicitly confirms
   the displayed booking details.
5. Never say an appointment is booked unless the booking tool
   returns success=true.
6. If a booking tool returns success=false, clearly explain that
   the booking was not completed. Never describe it as confirmed.
7. Never calculate or guess a weekday yourself. Use the exact
   date_display returned by the tool.
8. If a requested day is outside the doctor's working schedule,
   do not attempt to book it. Offer valid dates returned by the tools.

AUTHENTICATION AND PRIVACY
- The application injects the authenticated account ID into
  booking, lookup, and cancellation tools.
- Never ask the user for their account ID.
- Never guess, change, or override the authenticated account ID.
- Appointment lookup and cancellation must apply only to the
  currently logged-in account.
- Cancellation is handled by the application's separate
  confirmation workflow.

Do not claim that an operation succeeded unless the relevant
tool actually confirms success.
"""
    )

    history = [system_prompt]

    for message in st.session_state.messages:
        if message["role"] == "user":
            history.append(
                HumanMessage(content=message["content"])
            )
        elif message["role"] == "assistant":
            history.append(
                AIMessage(content=message["content"])
            )

    try:
        with st.chat_message("assistant"):
            with st.spinner("MediCare AI is thinking..."):
                response = llm.invoke(history)

                booking_result = None
                booking_tool_failed = False

                # Run the model's requested tools.
                for _ in range(5):
                    if not response.tool_calls:
                        break

                    history.append(response)

                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        is_booking = is_booking_tool(tool_name)

                        try:
                            result = execute_tool(
                                tool_name,
                                tool_call["args"],
                                supabase_user_id=supabase_user_id,
                            )

                            if not isinstance(result, dict):
                                result = {
                                    "success": False,
                                    "message": (
                                        "The tool returned an unexpected "
                                        "response."
                                    ),
                                }

                        except Exception as error:
                            print(
                                f"Tool execution error "
                                f"({tool_name}): {error}"
                            )

                            result = {
                                "success": False,
                                "message": (
                                    "The operation failed. "
                                    "Please check the details and try again."
                                ),
                            }

                            if is_booking:
                                booking_tool_failed = True

                        if is_booking:
                            booking_result = result

                        history.append(
                            ToolMessage(
                                content=json.dumps(
                                    result,
                                    default=str,
                                ),
                                tool_call_id=tool_call["id"],
                            )
                        )

                    response = llm.invoke(history)

                # A real booking-tool result takes priority over
                # AI-generated wording. This prevents the model from
                # inventing a weekday or claiming an unsuccessful
                # booking was successful.
                if booking_result is not None:
                    if (
                        booking_result.get("success") is True
                        and not booking_tool_failed
                    ):
                        reply = format_booking_success(
                            booking_result
                        )
                    else:
                        reply = format_booking_failure(
                            booking_result
                        )

                else:
                    reply = response.content

                    if isinstance(reply, list):
                        reply = "\n".join(
                            item.get("text", "")
                            for item in reply
                            if isinstance(item, dict)
                        )

                    if not isinstance(reply, str) or not reply.strip():
                        reply = (
                            "I couldn't complete that request. "
                            "Please try again."
                        )

                st.markdown(reply)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": reply,
            }
        )

    except Exception as error:
        print(f"Groq/chat error: {error}")

        error_message = (
            "I'm having trouble connecting to the AI service. "
            "Please check your Groq configuration and try again."
        )

        with st.chat_message("assistant"):
            st.error(error_message)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": error_message,
            }
        )
