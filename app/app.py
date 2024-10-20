import os
import openai
import anthropic
import streamlit as st
import sqlite3
from datetime import datetime, timedelta

openai_client = openai
openai_client.api_key = os.getenv("OPENAI_API_KEY")

anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)

# Database setup
def init_db():
    conn = sqlite3.connect('conversations.db')
    c = conn.cursor()
    
    # Create conversations table if it doesn't exist
    c.execute('''CREATE TABLE IF NOT EXISTS conversations
                 (id INTEGER PRIMARY KEY, title TEXT, timestamp TEXT)''')
    
    # Check if 'model' column exists, if not, add it
    c.execute("PRAGMA table_info(conversations)")
    columns = [column[1] for column in c.fetchall()]
    if 'model' not in columns:
        c.execute("ALTER TABLE conversations ADD COLUMN model TEXT")
    
    # Create messages table if it doesn't exist
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY, conversation_id INTEGER, 
                  role TEXT, content TEXT, timestamp TEXT,
                  FOREIGN KEY (conversation_id) REFERENCES conversations(id))''')
    
    conn.commit()
    return conn

def create_new_conversation(conn, title, model):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("INSERT INTO conversations (title, model, timestamp) VALUES (?, ?, ?)", (title, model, timestamp))
    conn.commit()
    return c.lastrowid

def get_conversations(conn):
    c = conn.cursor()
    c.execute("SELECT id, title, model, timestamp FROM conversations ORDER BY timestamp DESC")
    return c.fetchall()

def get_messages(conn, conversation_id):
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp", (conversation_id,))
    return c.fetchall()

def add_message(conn, conversation_id, role, content):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (conversation_id, role, content, timestamp))
    conn.commit()

def update_conversation_title(conn, conversation_id, new_title):
    c = conn.cursor()
    c.execute("UPDATE conversations SET title = ? WHERE id = ?", (new_title, conversation_id))
    conn.commit()

def is_conversation_empty(conn, conversation_id):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation_id,))
    count = c.fetchone()[0]
    return count == 0

def delete_conversation(conn, conversation_id):
    c = conn.cursor()
    # Delete messages associated with the conversation
    c.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    # Delete the conversation itself
    c.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()

def delete_if_empty(conn, conversation_id):
    if is_conversation_empty(conn, conversation_id):
        delete_conversation(conn, conversation_id)
        return True
    return False

def sidebar_warning(message):
    st.sidebar.warning(message)

def sidebar_success(message):
    st.sidebar.success(message)

def categorize_conversations(conversations):
    today = datetime.now().date()
    categories = {
        "Today": [],
        "Yesterday": [],
        "Last Week": [],
        "Last Month": [],
        "Before Last Month": []
    }

    for conv in conversations:
        try:
            conv_date = datetime.fromisoformat(conv[3]).date()  # Using the timestamp column (index 3)
        except ValueError:
            # If timestamp is invalid, use today's date as a fallback
            conv_date = today

        if conv_date == today:
            categories["Today"].append(conv)
        elif conv_date == today - timedelta(days=1):
            categories["Yesterday"].append(conv)
        elif today - timedelta(days=7) <= conv_date < today:
            categories["Last Week"].append(conv)
        elif today - timedelta(days=30) <= conv_date < today - timedelta(days=7):
            categories["Last Month"].append(conv)
        else:
            categories["Before Last Month"].append(conv)

    return categories

# Streamlit app
st.set_page_config(page_title="Mehdi-Bot", page_icon="🗨️")
st.markdown("<h1 style='text-align: center;'>Mehdi-Bot 🤓</h1>", unsafe_allow_html=True)

# Initialize database connection
conn = init_db()

# Initialize conversation_id
if 'current_conversation' not in st.session_state:
    st.session_state['current_conversation'] = None

# Sidebar for model selection and conversation management
with st.sidebar:
    # Area for warnings and messages
    warning_placeholder = st.empty()
    success_placeholder = st.empty()

    # Get the current conversation's model and title if one is selected
    current_model = None
    current_title = None
    if st.session_state['current_conversation']:
        c = conn.cursor()
        c.execute("SELECT model, title FROM conversations WHERE id = ?", (st.session_state['current_conversation'],))
        result = c.fetchone()
        if result:
            current_model, current_title = result

    st.header("Model Selection")

    # Model selection
    model_options = ["gpt-3.5-turbo", "gpt-4", "claude-3-sonnet-20240229"]
    model_display_names = {
        'gpt-3.5-turbo': 'GPT-3.5 Turbo',
        'gpt-4': 'GPT-4',
        'claude-3-sonnet-20240229': 'Claude 3.5 Sonnet',
    }

    def safe_get_model_name(model):
        if model is None or model.strip() == "":
            return "No Model"
        return model_display_names.get(model, model)

    if current_model and not is_conversation_empty(conn, st.session_state['current_conversation']):
        # If there's a non-empty conversation, force the model to be the current one
        selected_model = st.radio(
            "Current model (cannot be changed for ongoing conversations):",
            options=[current_model],
            format_func=safe_get_model_name,
            key="model_selection"
        )
        if current_model != selected_model:
            warning_placeholder.warning("You cannot change models in an ongoing conversation. Please start a new conversation to use a different model.")
    else:
        # Allow model selection for empty or new conversations
        selected_model = st.radio(
            label = " ",
            options = model_options,
            format_func = safe_get_model_name,
            key = "model_selection",
            index = model_options.index(current_model) if current_model in model_options else 0
        )

        if current_model and selected_model != current_model:
            # Update the model for the empty conversation
            c = conn.cursor()
            c.execute("UPDATE conversations SET model = ? WHERE id = ?", (selected_model, st.session_state['current_conversation']))
            conn.commit()
            success_placeholder.success(f"Model updated to {safe_get_model_name(selected_model)} for the current conversation.")

    st.header("Conversations")

    # New conversation button
    if st.button("Start New Conversation", key="new_conversation_button"):
        if st.session_state['current_conversation']:
            deleted = delete_if_empty(conn, st.session_state['current_conversation'])
            if deleted:
                success_placeholder.success("Empty conversation discarded.")

        current_date = datetime.now().strftime("%Y-%m-%d")
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM conversations WHERE DATE(timestamp) = DATE(?)", (current_date,))
        conversation_count = c.fetchone()[0] + 1
        new_title = f"Conversation {conversation_count} ({current_date})"
        new_id = create_new_conversation(conn, new_title, selected_model)
        st.session_state['current_conversation'] = new_id
        st.rerun()

    # Text input for changing conversation title
    new_title = st.text_input("Change title:", key="change_title_input")
    update_button = st.button("Update Title", key="update_title_button")

    if update_button:
        if st.session_state['current_conversation']:
            update_conversation_title(conn, st.session_state['current_conversation'], new_title)
            success_placeholder.success("Title updated successfully!")
            st.rerun()
        else:
            warning_placeholder.warning("Please select a conversation before updating the title.")

    # Display existing conversations
    conversations = get_conversations(conn)
    categorized_conversations = categorize_conversations(conversations)

    for category, convs in categorized_conversations.items():
        if convs:
            st.subheader(category)
            conversation_titles = {str(id): f"{title} ({safe_get_model_name(model)})" for id, title, model, _ in convs}
            selected_conversation = st.radio(
                f"Select conversation ({category})",
                options=list(conversation_titles.keys()),
                format_func=lambda x: conversation_titles[x],
                key=f"radio_{category}"
            )
            if selected_conversation:
                st.session_state['current_conversation'] = int(selected_conversation)
                current_model = [model for id, _, model, _ in convs if str(id) == selected_conversation][0]
                if current_model != selected_model:
                    warning_placeholder.warning(f"This conversation uses {safe_get_model_name(current_model)}. To use {safe_get_model_name(selected_model)}, please start a new conversation.")

    # Delete conversation button
    if st.button("Delete Conversation", key="delete_conversation_button"):
        if st.session_state['current_conversation']:
            delete_conversation(conn, st.session_state['current_conversation'])
            st.session_state['current_conversation'] = None
            st.success("Conversation deleted successfully!")
            st.rerun()
        else:
            st.warning("Please select a conversation to delete.")

# Main chat interface
if st.session_state['current_conversation'] is not None:
    conversation_id = st.session_state['current_conversation']
    c = conn.cursor()
    c.execute("SELECT model FROM conversations WHERE id = ?", (conversation_id,))
    conversation_model = c.fetchone()[0]
    messages = get_messages(conn, conversation_id)

    for message in messages:
        with st.chat_message(message[0]):
            st.markdown(message[1])

if prompt := st.chat_input("Ask me a question."):
    if st.session_state['current_conversation'] is None:
        # Create a new conversation
        new_id = create_new_conversation(conn, "Unnamed Conversation", selected_model)
        st.session_state['current_conversation'] = new_id
        conversation_id = new_id
        conversation_model = selected_model
    else:
        conversation_id = st.session_state['current_conversation']

    # Check if the current conversation is empty before adding the new message
    if is_conversation_empty(conn, conversation_id):
        # Update the conversation's model if it's empty
        c = conn.cursor()
        c.execute("UPDATE conversations SET model = ? WHERE id = ?", (selected_model, conversation_id))
        conn.commit()

    add_message(conn, conversation_id, "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        response = ""

        # Generate response using the conversation's model
        if conversation_model.startswith("gpt"):
            stream = openai_client.chat.completions.create(
                model=conversation_model,
                messages=[{"role": m[0], "content": m[1]} for m in get_messages(conn, conversation_id) + [("user", prompt)]],
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    response += chunk.choices[0].delta.content
                    response_placeholder.markdown(response + "▌")
            response_placeholder.markdown(response)

        elif selected_model.startswith("claude"):
            with anthropic_client.messages.stream(
                max_tokens=1024,
                messages=[{"role": m[0], "content": m[1]} for m in get_messages(conn, conversation_id) + [("user", prompt)]],
                model=selected_model,
            ) as stream:
                for text in stream.text_stream:
                    response += text
                    response_placeholder.markdown(response + "▌")
                response_placeholder.markdown(response)

        add_message(conn, conversation_id, "assistant", response)

    st.rerun()

# Close database connection
conn.close()