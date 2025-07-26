# Live Web Search AI Chatbot

An AI-powered chatbot that can search the web in real-time and provide informative responses using Groq LLM and Tavily search.

## Features

- Real-time web search capabilities
- Streaming responses for better user experience
- Chat history management
- Rate limiting for API protection
- Cross-Origin Resource Sharing (CORS) support

## Prerequisites

- Python 3.7 or higher
- Tavily API key (Get it from https://tavily.com/)
- Groq API key (Get it from https://console.groq.com/)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd LiveWeb-AI-Chatbot
```

2. Create and activate a virtual environment (recommended):
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

1. Create a `.env` file in the `backend` directory:
```
TAVILY_API_KEY=your_tavily_api_key_here
GROQ_API_KEY=your_groq_api_key_here
FRONTEND_ORIGIN=http://localhost:8501
PORT=8000
```

2. Make sure the chat history directories exist:
```bash
mkdir -p frontend/chat-history
mkdir -p backend/chat-history
```

## Running the Application

1. Start the backend server:
```bash
cd backend
python main.py
```

2. In a new terminal, start the frontend:
```bash
cd frontend
streamlit run app.py
```

The application will be available at:
- Frontend: http://localhost:8501
- Backend: http://localhost:8000

## Troubleshooting

1. **API Key Errors**
   - Verify that your `.env` file exists in the backend directory
   - Check that both API keys are valid and properly formatted
   - Try the `/health` endpoint (http://localhost:8000/health) to verify API key configuration

2. **CORS Errors**
   - Ensure FRONTEND_ORIGIN in `.env` matches your Streamlit URL
   - Default is http://localhost:8501

3. **Chat History Issues**
   - Verify that chat-history directories exist in both frontend and backend
   - Check file permissions
   - Clear chat history if corrupted

4. **Connection Errors**
   - Confirm both servers are running
   - Check if ports 8000 and 8501 are available
   - Verify network connectivity

5. **Rate Limiting**
   - By default, limited to 3 requests per IP
   - Modify the limit in `backend/main.py` if needed

## Development

- Backend runs on FastAPI with auto-reload enabled
- Frontend uses Streamlit for the UI
- Chat history uses Python's shelve module
- Rate limiting is implemented in-memory

## License

[Add your license information here]

