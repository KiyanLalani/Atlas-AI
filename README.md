# Atlas AI Assistant

A powerful AI document analysis assistant with a ChatGPT-like interface. Built with GPT-4o for advanced document understanding and natural conversation.

## Features

- 🎯 **Advanced Document Analysis**
  - Support for multiple file formats (PDF, DOC, DOCX, TXT, CSV, JSON)
  - Intelligent document understanding and context retention
  - Seamless document-based conversations

- 💬 **ChatGPT-Style Interface**
  - Clean, modern design matching OpenAI's ChatGPT
  - Smooth animations and transitions
  - Real-time message streaming
  - Conversation memory and context awareness

- 🚀 **Technical Features**
  - GPT-4o integration for state-of-the-art AI capabilities
  - 128,000 token context window
  - 16,384 token response length
  - Document content persistence between messages

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/atlas-ai.git
   cd atlas-ai
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up your environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key
   ```

5. Run the application:
   ```bash
   python app.py
   ```

## Deployment

### Deploy to Render.com

1. Fork this repository to your GitHub account

2. Create a new Web Service on Render.com:
   - Connect your GitHub repository
   - Select Python environment
   - Add environment variables:
     ```
     OPENAI_API_KEY=your_api_key_here
     PRODUCTION=true
     ```
   - Deploy!

### Manual Deployment

The application includes configuration for various deployment platforms:

- `render.yaml` for Render.com
- `Procfile` for Heroku
- `runtime.txt` for Python version specification
- `requirements.txt` for dependencies

## Development

### Project Structure

```
atlas-ai/
├── app.py              # Main Flask application
├── templates/          # HTML templates
│   └── index.html     # ChatGPT-style interface
├── static/            # Static assets
├── uploads/           # Temporary file storage
├── requirements.txt   # Python dependencies
└── .env              # Environment variables
```

### Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key
- `PRODUCTION`: Set to "true" in production
- `PORT`: Optional port number (default: 5000)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License - feel free to use this project for any purpose.

## Support

For support, please open an issue in the GitHub repository or contact the maintainers. 