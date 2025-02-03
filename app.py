from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from openai import OpenAI
from dotenv import load_dotenv
import os
import traceback
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from docx import Document
import json
import time
from functools import wraps

# Load environment variables only in development
if not os.getenv('PRODUCTION'):
    load_dotenv()

print(f"Starting application in {'production' if os.getenv('PRODUCTION') else 'development'} mode")

# Initialize Flask app
app = Flask(__name__, static_folder='static')
app.secret_key = os.urandom(24)  # For session management

# Enable debug mode in development
app.config['DEBUG'] = not os.getenv('PRODUCTION', False)

# Configure file upload settings
UPLOAD_FOLDER = '/tmp/uploads' if os.getenv('PRODUCTION') else 'uploads'
print(f"Upload folder configured as: {UPLOAD_FOLDER}")
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx', 'csv', 'json'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure OpenAI client
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    print("Warning: OPENAI_API_KEY not found in environment variables")
    client = None
else:
    try:
        client = OpenAI(
            api_key=api_key,
            max_retries=2,
            timeout=20.0,
            default_headers={
                "OpenAI-Beta": "assistants=v1"
            }
        )
        print("OpenAI client initialized successfully")
    except Exception as e:
        print(f"Error initializing OpenAI client: {e}")
        traceback.print_exc()
        client = None

# User database
USERS = {
    'SL': {
        'password': 'AI1',
        'is_admin': False,
        'full_name': 'Salma Lalani',
        'display_name': 'Salma'
    },
    'MH': {
        'password': 'AI2',
        'is_admin': False,
        'full_name': 'Michael Haggar',
        'display_name': 'Michael'
    },
    'Unknown': {
        'password': 'AI3',
        'is_admin': False,
        'full_name': 'Unknown User',
        'display_name': 'Unknown'
    },
    'KL': {
        'password': 'Admin',
        'is_admin': True,
        'full_name': 'Kiyan Lalani',
        'display_name': 'Kiyan'
    }
}

# Store chats in memory (in production, use a proper database)
CHATS = {}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USERS and USERS[username]['password'] == password:
            session['username'] = username
            session['is_admin'] = USERS[username]['is_admin']
            return redirect(url_for('index'))
        
        return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    username = session.get('username')
    is_admin = session.get('is_admin', False)
    user_info = USERS[username]
    
    # Get user's chats or all chats for admin
    if is_admin:
        user_chats = CHATS
    else:
        if username not in CHATS:
            CHATS[username] = {}
        user_chats = CHATS[username]
    
    return render_template('index.html',
                         username=username,
                         display_name=user_info['display_name'],
                         full_name=user_info['full_name'],
                         is_admin=is_admin,
                         chats=user_chats)

@app.route('/api/new-chat', methods=['POST'])
@login_required
def new_chat():
    username = session.get('username')
    
    # Initialize chat storage if needed
    if username not in CHATS:
        CHATS[username] = {}
    
    # Create new chat ID using timestamp
    new_chat_id = str(int(time.time()))
    CHATS[username][new_chat_id] = []
    
    # Save chats after creating new chat
    save_chats_to_file()
    
    return jsonify({
        'success': True,
        'chat_id': new_chat_id
    })

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    data = request.json
    user_input = data.get('message', '')
    chat_id = data.get('chat_id')
    file_content = data.get('file_content')
    
    username = session.get('username')
    print(f"Processing chat for user {username}, chat_id: {chat_id}")
    
    # Initialize chat storage if needed
    if username not in CHATS:
        CHATS[username] = {}
        print(f"Initialized chat storage for user {username}")
    
    # Create new chat if no chat_id provided
    if not chat_id:
        chat_id = str(int(time.time()))
        CHATS[username][chat_id] = []
        print(f"Created new chat {chat_id} for user {username}")
    
    # Ensure chat exists
    if chat_id not in CHATS[username]:
        CHATS[username][chat_id] = []
        print(f"Initialized chat {chat_id} for user {username}")
    
    # Add user message to chat history
    CHATS[username][chat_id].append({
        'role': 'user',
        'content': user_input,
        'timestamp': time.time()
    })
    
    # Save chats after adding user message
    save_chats_to_file()
    print(f"Saved chat after user message. Current chats: {json.dumps(CHATS, indent=2)}")
    
    try:
        # Generate AI response
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {'role': 'system', 'content': 'You are Atlas AI, a helpful assistant.'},
                *[{'role': msg['role'], 'content': msg['content']} for msg in CHATS[username][chat_id]]
            ],
            stream=True
        )
        
        def generate():
            response_content = ''
            for chunk in completion:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    response_content += content
                    yield f"data: {json.dumps({'content': content, 'chat_id': chat_id})}\n\n"
            
            # Save AI response to chat history
            CHATS[username][chat_id].append({
                'role': 'assistant',
                'content': response_content,
                'timestamp': time.time()
            })
            
            # Save chats after AI response
            save_chats_to_file()
            print(f"Saved chat after AI response. Current chats: {json.dumps(CHATS, indent=2)}")
            
        return generate(), {'Content-Type': 'text/event-stream'}
    
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def save_chats_to_file():
    """Save chats to a file for persistence"""
    try:
        with open('chats.json', 'w') as f:
            json.dump(CHATS, f, indent=2)
        print("Chats saved successfully")
    except Exception as e:
        print(f"Error saving chats: {e}")
        traceback.print_exc()

def load_chats_from_file():
    """Load chats from file on startup"""
    global CHATS
    try:
        if os.path.exists('chats.json'):
            with open('chats.json', 'r') as f:
                CHATS = json.load(f)
            print("Chats loaded successfully")
            print(f"Loaded chats: {json.dumps(CHATS, indent=2)}")
        else:
            print("No existing chats file found")
    except Exception as e:
        print(f"Error loading chats: {e}")
        traceback.print_exc()

# Load chats when the application starts
load_chats_from_file()

@app.route('/api/chat/<chat_id>')
@login_required
def get_chat(chat_id):
    username = session.get('username')
    is_admin = session.get('is_admin', False)
    
    if is_admin:
        # Admin can view any chat
        for user_chats in CHATS.values():
            if chat_id in user_chats and user_chats[chat_id]:
                return jsonify({'messages': user_chats[chat_id]})
    else:
        # Regular users can only view their own chats
        if username in CHATS and chat_id in CHATS[username] and CHATS[username][chat_id]:
            return jsonify({'messages': CHATS[username][chat_id]})
    
    return jsonify({'messages': []})

@app.route('/api/chats')
@login_required
def get_chats():
    username = session.get('username')
    is_admin = session.get('is_admin', False)
    
    if is_admin:
        chats_data = CHATS
    else:
        chats_data = CHATS.get(username, {})
    
    return jsonify({'chats': chats_data})

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_file_content(filepath):
    """Read content from different file types."""
    file_extension = filepath.split('.')[-1].lower()
    
    try:
        if file_extension == 'pdf':
            reader = PdfReader(filepath)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        
        elif file_extension in ['doc', 'docx']:
            doc = Document(filepath)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text
        
        elif file_extension == 'txt':
            with open(filepath, 'r', encoding='utf-8') as file:
                return file.read()
        
        elif file_extension == 'csv':
            with open(filepath, 'r', encoding='utf-8') as file:
                return file.read()
        
        elif file_extension == 'json':
            with open(filepath, 'r', encoding='utf-8') as file:
                return json.dumps(json.load(file), indent=2)
        
        return None
    except Exception as e:
        print(f"Error reading file {filepath}: {str(e)}")
        return None

@app.route('/health')
def health_check():
    """Health check endpoint for Render."""
    status = {
        'status': 'healthy',
        'timestamp': time.time(),
        'environment': 'production' if os.getenv('PRODUCTION') else 'development',
        'openai_client': 'initialized' if client is not None else 'not initialized',
        'upload_folder': UPLOAD_FOLDER,
        'upload_folder_exists': os.path.exists(UPLOAD_FOLDER)
    }
    print(f"Health check: {json.dumps(status)}")
    return jsonify(status)

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        print("Starting file upload process...")  # Debug print
        
        if 'file' not in request.files:
            print("No file part in request")  # Debug print
            return jsonify({'success': False, 'error': 'No file part'}), 400
        
        file = request.files['file']
        print(f"Received file: {file.filename}")  # Debug print
        
        if file.filename == '':
            print("No selected file")  # Debug print
            return jsonify({'success': False, 'error': 'No selected file'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            print(f"Saving file to: {filepath}")  # Debug print
            
            # Save the file
            file.save(filepath)
            print("File saved successfully")  # Debug print
            
            # Read file content
            print("Reading file content...")  # Debug print
            file_content = read_file_content(filepath)
            if file_content is None:
                print("Could not read file content")  # Debug print
                return jsonify({
                    'success': False,
                    'error': 'Could not read file content'
                }), 500
            
            print("File processed successfully")  # Debug print
            
            # Clean up the file after processing
            if os.getenv('PRODUCTION'):
                os.remove(filepath)
            
            return jsonify({
                'success': True,
                'filename': filename,
                'content': file_content[:1000] + "..." if len(file_content) > 1000 else file_content,
                'message': 'File uploaded and processed successfully'
            })
        else:
            print(f"File type not allowed: {file.filename}")  # Debug print
            return jsonify({
                'success': False,
                'error': f'File type not allowed. Allowed types are: {", ".join(ALLOWED_EXTENSIONS)}'
            }), 400

    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error occurred during file upload: {str(e)}")  # Debug print
        print(f"Traceback: {error_traceback}")  # Debug print
        return jsonify({
            'success': False,
            'error': f'Error uploading file: {str(e)}',
            'traceback': error_traceback
        }), 500

@app.route('/generate', methods=['POST'])
def generate():
    try:
        if client is None:
            return jsonify({
                'success': False,
                'error': 'OpenAI client is not initialized. Please check your API key.'
            }), 503

        data = request.json
        prompt = data.get('prompt')
        history = data.get('history', [])
        file_content = data.get('file_content')

        if not prompt:
            return jsonify({'success': False, 'error': 'No prompt provided'}), 400

        print(f"Processing request - Prompt: {prompt}")  # Debug print

        # Prepare messages with history and system prompt
        messages = [
            {"role": "system", "content": """You are Atlas AI, a highly capable AI assistant. You are helpful, knowledgeable, and precise in your responses. 
            When analyzing documents, you should:
            1. Provide clear, structured summaries
            2. Highlight key points and important information
            3. Answer questions specifically about the document's content
            4. If something is unclear or not mentioned in the document, say so"""}
        ]

        # Add conversation history
        messages.extend(history)

        # If there's file content, add it to the prompt with clear instructions
        if file_content:
            context_message = {
                "role": "user",
                "content": f"""Here is the content of the file:\n\n{file_content}\n\n
                Please analyze this document and respond to the following request: {prompt}"""
            }
            messages.append(context_message)
        else:
            messages.append({"role": "user", "content": prompt})
        
        print(f"Sending request to OpenAI with {len(messages)} messages")  # Debug print
        
        # Configure the completion with the latest options
        completion = client.with_options(timeout=30.0).chat.completions.create(
            model="gpt-4o",  # Using the base model which points to latest version
            messages=messages,
            temperature=0.7,
            max_tokens=16384,
            response_format={"type": "text"}
        )
        
        response_text = completion.choices[0].message.content
        print(f"Generated response: {response_text[:200]}...")  # Debug print truncated response
        
        return jsonify({
            'success': True,
            'response': response_text
        })

    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error occurred: {str(e)}")
        print(f"Traceback: {error_traceback}")
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_traceback
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    if os.getenv('PRODUCTION'):
        app.run(host='0.0.0.0', port=port)
    else:
        app.run(host='0.0.0.0', port=port, debug=True) 