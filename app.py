from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, Response
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
import requests
import random
import io

# Load environment variables only in development
if not os.getenv('PRODUCTION'):
    load_dotenv()

print(f"Starting application in {'production' if os.getenv('PRODUCTION') else 'development'} mode")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_courtlistener",
            "description": "Searches CourtListener for legal opinions and filings. Use this tool to find relevant case law or legal documents based on search terms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to use on CourtListener.  Be specific and include relevant keywords."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_random_number",
            "description": "Generates a random number within a specified range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_value": {
                        "type": "integer",
                        "description": "The minimum value for the random number (inclusive)."
                    },
                    "max_value": {
                        "type": "integer",
                        "description": "The maximum value for the random number (inclusive)."
                    }
                },
                "required": ["min_value", "max_value"]
            }
        }
    }
]

def generate_random_number(min_value: int, max_value: int) -> int:
    """Generates a random number within a specified range."""
    return random.randint(min_value, max_value)

class CourtListenerSearch:
    def __init__(self):
        self.api_token = os.getenv('COURTLISTENER_API_TOKEN')
        self.base_url = "https://www.courtlistener.com/api/rest/v3"
        self.headers = {"Authorization": f"Token {self.api_token}"}
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # List of user agents to rotate through
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edge/120.0.0.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
    def search_cases(self, query):
        endpoint = f"{self.base_url}/search/"
        params = {
            "q": query,
            "type": "o"  # opinions
        }
        response = requests.get(endpoint, headers=self.headers, params=params)
        if response.status_code != 200:
            print(f"Error: API request failed with status {response.status_code}")
            return None
        return response.json()
    
    def get_case_by_cite(self, citation):
        endpoint = f"{self.base_url}/search/"
        params = {
            "cite": citation,
            "type": "o"
        }
        response = requests.get(endpoint, headers=self.headers, params=params)
        if response.status_code != 200:
            print(f"Error: API request failed with status {response.status_code}")
            return None
        return response.json()

    def scrape_case_text(self, url, document_url):
        if not document_url:
            print("Warning: No document URL provided. Cannot download case text.")
            return None
        try:
            print(f"Attempting to download PDF from: {document_url}")
            user_agent = random.choice(self.user_agents)
            headers = {'User-Agent': user_agent}
            
            # Download PDF using the document URL
            pdf_response = requests.get(document_url, headers=headers)
            pdf_response.raise_for_status()
            if not pdf_response.content:
                print("Warning: PDF content is empty.")
            
            # Read PDF content
            pdf_file = io.BytesIO(pdf_response.content)
            pdf_reader = PdfReader(pdf_file)
            
            # Extract text from all pages
            text = ""
            for i, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text
                else:
                    print(f"Warning: No text found on page {i} of the PDF.")
            
            if text.strip():
                print(f"Successfully extracted text from PDF, character count: {len(text.strip())}")
                return text.strip()
            else:
                print("Warning: PDF text extraction yielded no usable text.")
                return None
                    
        except Exception as e:
            print(f"Error downloading PDF: {str(e)}")
            return None

    def format_case_output(self, result):
        print(f"\nCase: {result.get('caseName')}")
        print(f"Citation: {result.get('citation', 'N/A')}")
        print(f"Court: {result.get('court_name', 'N/A')}")
        print(f"Date: {result.get('dateFiled', 'N/A')}")
        
        # Get the absolute URL
        absolute_url = result.get('absolute_url')
        if absolute_url:
            print(f"Link: https://www.courtlistener.com{absolute_url}")
        
        # Get PDF URL if available
        pdf_url = result.get('pdf_url')
        if pdf_url:
            print(f"PDF: {pdf_url}")
            
        # Get local path if available and construct document URL
        local_path = result.get('local_path')
        document_url = None
        if local_path:
            document_url = f"https://storage.courtlistener.com/{local_path}"
            print(f"Document: {document_url}")
        else:
            document_url = pdf_url  # Fallback to pdf_url if local path is not available
        
        return absolute_url, document_url

def search_courtlistener(query):
    """Use the CourtListenerSearch class to perform a search and return results."""
    cls = CourtListenerSearch()
    results = cls.search_cases(query)
    if not results or 'results' not in results:
        return "No results found or API error occurred"
    
    found_cases = results.get("results", [])[:5]
    if not found_cases:
        return "No matching cases found"
    
    case_texts = []
    for result in found_cases:
        url, document_url = cls.format_case_output(result)
        if url:
            case_text = cls.scrape_case_text(url, document_url)
            if case_text:
                case_texts.append(case_text)
    
    return "\n\n".join(case_texts)

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
        # If no chats exist for the user, create a default chat
        if not CHATS[username]:
            new_chat_id = str(int(time.time()))
            CHATS[username][new_chat_id] = []
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
        messages = [
            {'role': 'system', 'content': 'You are Atlas AI, a helpful assistant. You have access to tools, and in generate random number theres a min and max you have to fill out otherwise people will die and you have to fill out the query param of courtlistener YOU COME UP WITH THE KEYWORDS YOURSELF FOR COURTLISTENER FOR SEARCH. (do very surface level terms ie drugs or ai or stuff like that, dont say extra words since the search engine is very basic) If you use a tool and get results, summarize those results in your final response to the user.'},
            *[{'role': msg['role'], 'content': msg['content']} for msg in CHATS[username][chat_id]]
        ]
        
        # First, check if tool usage is likely needed
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        
        # Check if there are any tool calls in the response
        if completion.choices[0].message.tool_calls:
            # Process non-streaming tool calls
            tool_calls = completion.choices[0].message.tool_calls
            response_content = completion.choices[0].message.content or ""
            
            # Process each tool call
            for tool_call in tool_calls:
                tool_call_id = tool_call.id
                function_name = tool_call.function.name
                
                try:
                    tool_arguments_str = tool_call.function.arguments
                    function_args = json.loads(tool_arguments_str) if tool_arguments_str else {}
                except json.JSONDecodeError as e:
                    print(f"JSONDecodeError: {e}")
                    print(f"Faulty JSON: {tool_call.function.arguments}")
                    return jsonify({'error': 'Failed to parse tool arguments. Please try again.'}), 500
                
                if function_name == "search_courtlistener":
                    search_query = function_args.get("query")
                    if search_query is None:
                        print("Error: Missing 'query' parameter for search_courtlistener.")
                        return jsonify({'error': 'Missing query parameter for search_courtlistener.'}), 500
                    
                    search_results = search_courtlistener(search_query)
                    summary = summarize_tool_results(search_results, search_query)
                    
                    CHATS[username][chat_id].append({
                        'role': 'assistant',
                        'name': function_name,
                        'content': summary,
                        'tool_call_id': tool_call_id,
                        'timestamp': time.time()
                    })
                
                elif function_name == "generate_random_number":
                    min_value = function_args.get("min_value")
                    max_value = function_args.get("max_value")
                    
                    if min_value is None or max_value is None:
                        print(f"Error: min_value or max_value is None for generate_random_number. Args: {function_args}")
                        return jsonify({'error': 'Invalid arguments for random number generation.'}), 500
                    
                    if not isinstance(min_value, int) or not isinstance(max_value, int):
                        print(f"Error: min_value or max_value is not an integer. min_value: {min_value}, max_value: {max_value}")
                        return jsonify({'error': 'Invalid argument types for random number generation.'}), 500
                    
                    random_number = generate_random_number(min_value, max_value)
                    
                    CHATS[username][chat_id].append({
                        'role': 'assistant',
                        'name': function_name,
                        'content': str(random_number),
                        'tool_call_id': tool_call_id,
                        'timestamp': time.time()
                    })
            
            # After tool calls, get final response with tool outputs
            final_messages = messages.copy()
            for msg in CHATS[username][chat_id]:
                if msg['role'] == 'assistant' and 'tool_call_id' in msg:
                    final_messages.append({
                        'role': 'assistant',
                        'tool_call_id': msg['tool_call_id'],
                        'name': msg['name'],
                        'content': msg['content']
                    })
            
            final_completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=final_messages,
                stream=True
            )
            
            def generate():
                nonlocal response_content
                for chunk in final_completion:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content = delta.content
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
            
            return Response(generate(), content_type='text/event-stream')
            
        else:
            # No tool calls needed, just stream the response
            streaming_completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                stream=True
            )
            
            def generate():
                response_content = ''
                for chunk in streaming_completion:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content = delta.content
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
            
            return Response(generate(), content_type='text/event-stream')
    
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def summarize_tool_results(tool_results, query):
    """Summarizes the results from a tool call using another OpenAI completion."""
    try:
        prompt = f"Please summarize the following search results from CourtListener, based on the query '{query}'. Focus on the most relevant information.\n\n{tool_results}"
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes search results BE EXTREMELY IN DETAIL"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error summarizing tool results: {e}")
        return "Error summarizing tool results."

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
            4. If something is unclear or not mentioned in the document, say so
            You have access to tools, and in generate random number there's a min and max you have to fill out otherwise people will die and you have to fill out the query param of courtlistener. YOU COME UP WITH THE KEYWORDS YOURSELF FOR COURTLISTENER FOR SEARCH."""}
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
            model="gpt-4o-mini",  # Using the base model which points to latest version
            messages=messages,
            temperature=0.7,
            max_tokens=16384,
            tools=TOOLS,
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