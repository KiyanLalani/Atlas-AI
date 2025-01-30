# Atlas AI Assistant

A powerful AI assistant that can analyze documents and answer questions using GPT-4.

## Features

- Document analysis (PDF, DOC, DOCX, TXT, CSV, JSON)
- Conversation memory
- File upload and processing
- Clean, modern interface

## Deployment Instructions

1. Create a Heroku account at https://signup.heroku.com/

2. Install the Heroku CLI:
   ```bash
   # For macOS
   brew tap heroku/brew && brew install heroku

   # For Windows
   # Download installer from: https://devcenter.heroku.com/articles/heroku-cli
   ```

3. Login to Heroku:
   ```bash
   heroku login
   ```

4. Create a new Heroku app:
   ```bash
   heroku create your-app-name
   ```

5. Set environment variables:
   ```bash
   heroku config:set OPENAI_API_KEY=your_openai_api_key
   heroku config:set PRODUCTION=true
   ```

6. Deploy the application:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git push heroku main
   ```

7. Open the application:
   ```bash
   heroku open
   ```

## Local Development

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a .env file with your OpenAI API key:
   ```
   OPENAI_API_KEY=your_key_here
   ```

4. Run the application:
   ```bash
   python app.py
   ```

## Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key
- `PRODUCTION`: Set to "true" in production environment

## License

MIT License 