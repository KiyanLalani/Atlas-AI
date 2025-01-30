from flask import Flask, render_template, request, jsonify, send_from_directory
from openai import OpenAI
from dotenv import load_dotenv
import os
import traceback
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from docx import Document
import json
import time

# Load environment variables only in development
if not os.getenv('PRODUCTION'):
    load_dotenv()

print(f"Starting application in {'production' if os.getenv('PRODUCTION') else 'development'} mode")

# Initialize Flask app
app = Flask(__name__, static_folder='static')

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

@app.route('/')
def home():
    return render_template('index.html')

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