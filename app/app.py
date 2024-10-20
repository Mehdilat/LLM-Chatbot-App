import os
import openai
import anthropic
import streamlit as st

st.set_page_config(page_title="🗨️ Mehdi-Bot", page_icon="🗨️")
st.title("Mehdi-Bot 🤓")

openai_client = openai
openai_client.api_key = os.getenv("OPENAI_API_KEY")

anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)

if "selected_model" not in st.session_state:
    st.session_state["selected_model"] = "OpenAI GPT-3.5 Turbo"

if "messages" not in st.session_state:
    st.session_state.messages = []

selected_model = st.sidebar.radio(
    "Select Model:",
    options=["OpenAI GPT-3.5 Turbo", "OpenAI GPT-4o", "Anthropic Claude 3.5 Sonnet"],
)

st.session_state["selected_model"] = selected_model

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("What is up?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        response = ""

        if st.session_state["selected_model"].startswith("OpenAI"):
            model_name = "gpt-3.5-turbo" if selected_model == "OpenAI GPT-3.5 Turbo" else "gpt-4o"
            stream = openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ],
                stream=True,
            )
            response = st.write_stream(stream)
        
        elif st.session_state["selected_model"] == "Anthropic Claude 3.5 Sonnet":
            model_name = "claude-3-5-sonnet-20240620"
            with anthropic_client.messages.stream(
                max_tokens=1024,
                messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
                model=model_name,
            ) as stream:
                for text in stream.text_stream:
                    response += str(text) if text is not None else ""
                    response_placeholder.markdown(response + "▌")
                    response_placeholder.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})