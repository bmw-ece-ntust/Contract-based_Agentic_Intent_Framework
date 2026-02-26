import json
import requests
import streamlit as st
from requests.exceptions import RequestException

st.set_page_config(page_title="Chat Demo", page_icon="💬")

if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("Intent-Based Network 💬")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

with st.form("chat_form", clear_on_submit=True):
    prompt = st.text_area("Enter your message", height=120, placeholder="Please enter your message here...")
    submitted = st.form_submit_button("Submit")

if submitted and prompt.strip():
    user_text = prompt.strip()
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.spinner("Waiting for response..."):
        try:
            response = requests.post(
                "http://localhost:5200/human_language",
                json={"message": user_text},
                timeout=200,
            )
            response.raise_for_status()
            try:
                payload = response.json()
                bot_text = payload.get("response") or payload.get("message") or json.dumps(payload, ensure_ascii=False)
            except ValueError:
                bot_text = response.text.strip() or "(Empty Response)"
        except RequestException as exc:
            bot_text = f"⚠️ Request failed: {exc}"

    st.session_state.messages.append({"role": "assistant", "content": bot_text})
    with st.chat_message("assistant"):
        st.markdown(bot_text)
