import os
import json
import boto3
import streamlit as st
import uuid
import hashlib
import hmac
import base64
from datetime import datetime
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
from utils.agentcore_memory_manager import create_agentcore_memory_manager

# Load environment variables from .env file
load_dotenv()

# Cognito Configuration
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET")
COGNITO_REGION = os.getenv("COGNITO_REGION")

@st.cache_resource
def get_cognito_client():
    """Initialize Cognito client"""
    return boto3.client('cognito-idp', region_name=COGNITO_REGION)

def calculate_secret_hash(username, client_id, client_secret):
    """Calculate secret hash for Cognito"""
    message = username + client_id
    dig = hmac.new(client_secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
    return base64.b64encode(dig).decode()

def authenticate_user(username, password):
    """Authenticate user with Cognito"""
    cognito_client = get_cognito_client()
    
    try:
        secret_hash = calculate_secret_hash(username, COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET)
        
        response = cognito_client.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password,
                'SECRET_HASH': secret_hash
            }
        )
        
        return True, response.get('AuthenticationResult', {})
    except ClientError as e:
        return False, str(e)

def login_ui():
    """Display login form"""
    st.title("🔐 Customer Support Agent Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            if username and password:
                success, result = authenticate_user(username, password)
                if success:
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.auth_tokens = result
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error(f"Login failed: {result}")
            else:
                st.error("Please enter both username and password")

@st.cache_resource
def get_agent_clients():
    """Initialize agent clients once and cache them"""
    agent_core_client = boto3.client('bedrock-agentcore', region_name="us-east-1",
                                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    
    control_client = boto3.client('bedrock-agentcore-control', region_name="us-east-1",
                                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    return agent_core_client, control_client

@st.cache_data
def load_deployment_info():
    """Load deployment info from JSON file"""
    with open('deployment_info.json', 'r') as f:
        return json.load(f)

def get_session_manager():
    """Initialize AgentCore memory manager"""
    if 'session_manager' not in st.session_state:
        deployment_info = load_deployment_info()
        st.session_state.session_manager = create_agentcore_memory_manager(
            region=deployment_info.get('gateway_region', 'us-east-1')
        )
    return st.session_state.session_manager

def agentcore_runtime_invokation(query):
    """Invoke the AgentCore runtime with memory-enhanced query"""
    deployment_info = load_deployment_info()
    runtime_arn = deployment_info['agentcore_runtime_arn']
    
    agent_core_client, _ = get_agent_clients()
    session_manager = get_session_manager()
    
    if 'session_id' not in st.session_state:
        st.session_state.session_id = f"session-{uuid.uuid4()}"
    
    user_id = st.session_state.get('username', 'anonymous')
    
    # Get conversation context and user preferences
    conversation_context = session_manager.get_conversation_context(user_id, st.session_state.session_id, query)
    user_preferences = session_manager.get_user_preferences(user_id)
    
    # Enhance query with context
    enhanced_query = query
    if conversation_context:
        enhanced_query = f"Context from previous conversations:\n{conversation_context}\n\nUser preferences: {json.dumps(user_preferences)}\n\nCurrent query: {query}"
    
    payload = json.dumps({"prompt": enhanced_query}).encode('utf-8')

    try:
        response = agent_core_client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=st.session_state.session_id,
            payload=payload,
            qualifier="DEFAULT"
        )
        
        response_body = response['response'].read()
        response_data = json.loads(response_body)
        
        if isinstance(response_data, str):
            cleaned_response = response_data.replace('\n\n\n', '\n\n')
            cleaned_response = cleaned_response.replace('                    ', '')
            
            # Store in AgentCore memory
            session_manager.store_message(user_id, st.session_state.session_id, query, cleaned_response)
            
            return cleaned_response
        
        response_str = str(response_data)
        # Store in AgentCore memory
        session_manager.store_message(user_id, st.session_state.session_id, query, response_str)
        
        return response_str
        
    except Exception as e:
        st.error(f"Error invoking agent runtime: {str(e)}")
        return "I apologize, but I'm experiencing technical difficulties. Please try again in a moment."

# Check authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login_ui()
    st.stop()

# Main UI for authenticated users
st.title("🤖 Customer Support Agent")
st.markdown("""Ask questions about:
- 🏢 **Customer Profiles** - Look up customer information by ID, email, or phone
- 🛡️ **Warranty Status** - Check product warranties using serial numbers  
- 🌍 **Mars Weather** - Get current atmospheric data from Mars
- 🔍 **Web Search** - Find current news, information, and updates on any topic
""")

# Initialize session if not exists
if 'session_id' not in st.session_state:
    session_manager = get_session_manager()
    user_id = st.session_state.get('username', 'anonymous')
    st.session_state.session_id = session_manager.create_session(user_id)

# Initialize chat history if not exists
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# Initialize delete confirmation states
if 'delete_confirmations' not in st.session_state:
    st.session_state.delete_confirmations = {}

# Sidebar with session management
with st.sidebar:
    st.write(f"Welcome, {st.session_state.get('username', 'User')}!")
    
    if st.session_state.get('authenticated'):
        session_manager = get_session_manager()
        user_id = st.session_state.get('username', 'anonymous')
        
        # Session Management
        st.subheader("💬 Chat Sessions")
        
        # New Session Button
        if st.button("➕ New Chat Session", key="new_session_btn"):
            new_session_id = session_manager.create_session(user_id)
            st.session_state.session_id = new_session_id
            st.session_state.chat_history = []
            st.success("New session started!")
            st.rerun()
        
        # Get user sessions with error handling
        try:
            user_sessions = session_manager.get_user_sessions(user_id, limit=10)
        except Exception as e:
            st.error(f"Error loading sessions: {str(e)}")
            user_sessions = []
        
        # Always show current session in the list
        current_session_id = st.session_state.get('session_id', '')
        if current_session_id and not any(s.get('session_id') == current_session_id for s in user_sessions):
            # Add current session to the list if not present
            user_sessions.insert(0, {
                'session_id': current_session_id,
                'last_message': 'Current session',
                'last_updated': datetime.now().isoformat()
            })
        
        if user_sessions:
            st.write("**Chat Sessions:**")
            for i, session in enumerate(user_sessions):
                session_id = session.get('session_id', '')
                last_updated = session.get('last_updated', '')
                last_message = session.get('last_message', 'No messages')
                
                # Create session title from last message or timestamp
                if last_message and last_message != 'No messages' and last_message != 'New session started':
                    session_title = last_message[:25] + "..." if len(last_message) > 25 else last_message
                else:
                    # Use timestamp for title
                    try:
                        if last_updated:
                            date_part = last_updated[:10] if 'T' in last_updated else last_updated[:10]
                            session_title = f"Chat {date_part}"
                        else:
                            session_title = f"Session {i+1}"
                    except:
                        session_title = f"Session {i+1}"
                
                # Session row with button and delete option
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    # Session button with current session indicator
                    current_session = st.session_state.get('session_id', '')
                    if session_id == current_session:
                        button_label = f"▶️ {session_title} (Active)"
                        button_type = "primary"
                    else:
                        button_label = f"💬 {session_title}"
                        button_type = "secondary"
                    
                    if st.button(button_label, key=f"session_{session_id[:8]}_{i}", type=button_type):
                        if session_id != current_session:
                            # Switch to selected session
                            st.session_state.session_id = session_id
                            
                            # Load session messages from AgentCore memory
                            try:
                                messages = session_manager.get_session_messages(user_id, session_id)
                                
                                # Reconstruct chat history for UI
                                st.session_state.chat_history = []
                                current_query = None
                                
                                for msg in messages:
                                    if msg['role'] == 'user':
                                        current_query = msg['content']
                                    elif msg['role'] == 'assistant' and current_query:
                                        st.session_state.chat_history.append({
                                            'query': current_query,
                                            'response': msg['content']
                                        })
                                        current_query = None
                                
                                st.success(f"Switched to: {session_title}")
                            except Exception as e:
                                st.error(f"Error loading session: {str(e)}")
                            
                            st.rerun()
                
                with col2:
                    # Delete button (only for non-active sessions)
                    if session_id != current_session:
                        if st.button("🗑️", key=f"delete_{session_id[:8]}_{i}", help="Delete session"):
                            st.session_state[f"confirm_delete_{session_id}"] = True
                            st.rerun()
                
                # Confirmation dialog
                if st.session_state.get(f"confirm_delete_{session_id}", False):
                    st.warning(f"⚠️ Delete '{session_title}'?")
                    col_yes, col_no = st.columns(2)
                    
                    with col_yes:
                        if st.button("✅ Yes", key=f"yes_{session_id[:8]}_{i}"):
                            try:
                                # Get fresh session manager to avoid cache issues
                                session_manager = get_session_manager()
                                
                                # Check if method exists
                                if not hasattr(session_manager, 'delete_session'):
                                    st.error("Delete method not available. Please refresh the page.")
                                else:
                                    success = session_manager.delete_session(user_id, session_id)
                                    if success:
                                        st.success(f"Deleted: {session_title}")
                                    else:
                                        st.error("Failed to delete session")
                            except AttributeError as e:
                                st.error(f"Method not found: {str(e)}. Please refresh the page.")
                            except Exception as e:
                                st.error(f"Error deleting session: {str(e)}")
                            
                            # Clear confirmation state
                            st.session_state[f"confirm_delete_{session_id}"] = False
                            st.rerun()
                    
                    with col_no:
                        if st.button("❌ No", key=f"no_{session_id[:8]}_{i}"):
                            st.session_state[f"confirm_delete_{session_id}"] = False
                            st.rerun()
        else:
            st.write("**No previous sessions found**")
            st.write("Start a conversation to create your first session!")
        
        st.divider()
        
        # Display user preferences
        preferences = session_manager.get_user_preferences(user_id)
        st.subheader("👤 Your Profile")
        if preferences.get('common_issues'):
            st.write("**Common Topics:**")
            for issue in preferences['common_issues'][:3]:
                st.write(f"• {issue.title()}")
        
        if preferences.get('preferred_topics'):
            st.write("**Interests:**")
            for topic in preferences['preferred_topics'][:3]:
                st.write(f"• {topic.replace('_', ' ').title()}")
    
    st.divider()
    
    # Debug: Clear cache button
    if st.button("🔄 Refresh", help="Clear cache and refresh session manager"):
        if 'session_manager' in st.session_state:
            del st.session_state.session_manager
        st.rerun()
    
    if st.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.pop('username', None)
        st.session_state.pop('auth_tokens', None)
        st.session_state.pop('session_id', None)
        st.session_state.pop('chat_history', None)
        if 'session_manager' in st.session_state:
            del st.session_state.session_manager
        st.rerun()

# Sample queries based on available tools and services
sample_queries = {
    # Customer Profile Queries
    "👤 John Smith Profile": "Can you look up customer profile for customer_id CUST001?",
    "📧 Email Lookup": "Find customer profile for email john.smith@email.com",
    "📞 Phone Lookup": "Look up customer with phone +1-555-0102",
    
    # Warranty Status Queries
    "🛡️ Gaming Console Warranty": "Check warranty status for serial number MNO33333333",
    "📱 SmartPhone Warranty": "What's the warranty status for serial ABC12345678?",
    "💻 Laptop Warranty": "Check warranty for my Laptop Ultra with serial DEF98765432",
    "🎧 Headphones Warranty": "Warranty check for Wireless Headphones Elite serial GHI11111111",
    "⌚ Smart Watch Warranty": "Is my Smart Watch Series X still under warranty? Serial JKL22222222",
    "📺 Smart TV Warranty": "Check warranty for Smart TV 65\" OLED serial STU55555555",
    "🔊 Speaker Warranty": "Warranty status for Bluetooth Speaker Pro serial VWX66666666",
    
    # Mars Weather Queries
    "🌍 Mars Weather": "What is the current weather on Mars?",
    "🌡️ Mars Temperature": "What's the temperature on Mars today?",
    
    # Web Search Queries
    "🔍 Latest Tech News": "Search for the latest technology news and trends",
    "📰 Current Events": "What are the current major news events happening today?",
    "🚀 Space News": "Find recent news about space exploration and NASA missions",
    "💼 Company Research": "Search for information about Amazon Web Services latest announcements",
    "🏆 Sports Updates": "What are the latest sports news and scores?",
    "🌐 Web Trends": "Search for current web development trends and technologies",
    "📊 Market News": "Find the latest stock market and financial news",
    "🎮 Gaming News": "Search for recent gaming industry news and releases"
}

# Sample queries section
st.subheader("📋 Sample Queries")
st.markdown("Try these sample queries to explore different capabilities:")

# Customer Profile Queries
st.write("**🏢 Customer Profile Lookups:**")
cols1 = st.columns(3)
profile_queries = list(sample_queries.items())[:3]
for i, (label, query) in enumerate(profile_queries):
    with cols1[i]:
        if st.button(label, key=f"profile_{i}"):
            st.session_state.user_query = query

# Warranty Queries
st.write("**🛡️ Warranty Status Checks:**")
cols2 = st.columns(4)
warranty_queries = list(sample_queries.items())[3:10]
for i, (label, query) in enumerate(warranty_queries):
    with cols2[i % 4]:
        if st.button(label, key=f"warranty_{i}"):
            st.session_state.user_query = query

# Mars Weather Queries
st.write("**🌍 Mars Weather Data:**")
cols3 = st.columns(2)
mars_queries = list(sample_queries.items())[10:12]
for i, (label, query) in enumerate(mars_queries):
    with cols3[i % 2]:
        if st.button(label, key=f"mars_{i}"):
            st.session_state.user_query = query

# Web Search Queries
st.write("**🔍 Web Search Queries:**")
cols4 = st.columns(4)
web_search_queries = list(sample_queries.items())[12:]
for i, (label, query) in enumerate(web_search_queries):
    with cols4[i % 4]:
        if st.button(label, key=f"websearch_{i}"):
            st.session_state.user_query = query

# Display current session chat history first
if st.session_state.chat_history:
    st.subheader(f"📝 Current Session ({st.session_state.session_id[:8]}...)")
    for i, chat in enumerate(st.session_state.chat_history):
        # User message
        with st.chat_message("user"):
            st.write(chat['query'])
        
        # Assistant response
        if chat.get('response'):
            with st.chat_message("assistant"):
                st.write(chat['response'])

# Query input - always visible
user_query = st.text_area(
    "Enter your question:",
    value=st.session_state.get('user_query', ''),
    height=100,
    placeholder="Ask about customer profiles, warranty status, Mars weather, or search the web for current information...",
    key="main_query_input"
)

# Submit button
if st.button("🚀 Ask Agent", type="primary", key="ask_agent_btn"):
    if user_query.strip():
        session_manager = get_session_manager()
        user_id = st.session_state.get('username', 'anonymous')
        
        with st.spinner("Processing your request..."):
            response = agentcore_runtime_invokation(user_query)
        
        # Add to chat history
        chat_entry = {"query": user_query, "response": response}
        st.session_state.chat_history.append(chat_entry)
        
        # Clear the input for next query
        st.session_state.user_query = ""
        
        # Store follow-up questions in session state to prevent disappearing
        if 'follow_up_questions' not in st.session_state:
            st.session_state.follow_up_questions = []
        
        # Generate and store follow-up questions
        try:
            follow_ups = session_manager.generate_follow_up_questions(user_id, user_query)
            if follow_ups:
                st.session_state.follow_up_questions = follow_ups
        except Exception as e:
            st.error(f"Error generating follow-ups: {str(e)}")
            st.session_state.follow_up_questions = []
        
        st.rerun()
    else:
        st.warning("Please enter a question first!")

# Display persistent follow-up questions
if st.session_state.get('follow_up_questions'):
    st.subheader("🔄 Suggested Follow-up Questions")
    cols = st.columns(min(len(st.session_state.follow_up_questions), 3))
    for i, follow_up in enumerate(st.session_state.follow_up_questions):
        with cols[i % 3]:
            if st.button(follow_up, key=f"persistent_followup_{i}"):
                st.session_state.user_query = follow_up
                # Clear follow-ups after selection
                st.session_state.follow_up_questions = []
                st.rerun()

# Clear history button
if st.session_state.chat_history:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Clear Current Session", key="clear_history_btn"):
            st.session_state.chat_history = []
            st.session_state.follow_up_questions = []
            st.rerun()
    with col2:
        if st.button("❌ Clear Follow-ups", key="clear_followups_btn"):
            st.session_state.follow_up_questions = []
            st.rerun()