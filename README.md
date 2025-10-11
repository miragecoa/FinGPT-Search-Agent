# FinGPT Search Agents

Vision: A financial agent to assist users in information retrieval and data analysis. It provides the information sources of generated responses to help users evaluate the responses' quality.

This is a demo of FinLLM Leaderboard on HuggingFace's [Open Financial LLM Leaderboard](https://huggingface.co/spaces/TheFinAI/Open-Financial-LLM-Leaderboard).

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10+
- Node.js 14+
- Git

### Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd FinGPT-Search-Agent
   ```

2. **Install Python dependencies**:
   ```bash
   python scripts/install_all.py
   # or
   make install
   ```

3. **Install FinGPT-Desktop dependencies**:
   ```bash
   cd FinGPT-desktop
   npm install
   cd ..
   ```

### 🔧 Starting the System

**Important**: You must start services in this specific order for WebSocket connections to work properly.

#### Step 0: Activate the Python Virtual Environment
FinGPTenv\Scripts\activate
FinGPTenv\Scripts\Activate.ps1

#### Step 1: Start MCP Server
```bash
cd mcp-server
python server.py
```
- Server will run on `http://127.0.0.1:9000`
- Provides browser_navigate and other tools

#### Step 2: Start Django Backend (ASGI)
```bash
cd Main/backend
daphne -b 127.0.0.1 -p 8000 django_config.asgi:application
```
- **Important**: Use `daphne` (ASGI server), NOT `python manage.py runserver` (WSGI)
- WSGI servers don't support WebSocket connections
- Server will run on `http://127.0.0.1:8000`

#### Step 3: Start FinGPT-Desktop Application
```bash
cd FinGPT-desktop
npm start
```
- Electron desktop application will launch
- Should automatically connect to the backend

### ✅ Verification

1. **Check MCP Server**: Visit `http://127.0.0.1:9000` - should show FastMCP interface
2. **Check Django Backend**: Look for WebSocket connection logs:
   ```
   WSCONNECTING /ws/chat/
   WSCONNECT /ws/chat/
   Chat WebSocket connected
   ```
3. **Check Desktop App**: Status should show "Connected"

### 🤖 Agent Mode Features

The system now includes an advanced Agent Mode with tool calling capabilities:

#### Features
- **Browser Navigate Tool**: Navigate to URLs and extract page information
- **Multi-turn Conversations**: Complex reasoning with tool usage
- **Real-time Tool Status**: See tool calling progress in real-time
- **Context Management**: Maintains conversation history with R2C compression

#### Usage
1. Open FinGPT-Desktop application
2. ✅ Check "Agent Mode" checkbox
3. Ask questions that involve web navigation:
   ```
   Navigate to https://httpbin.org/get and tell me what you find
   ```

#### Expected Behavior
When using Agent Mode, you'll see:
1. **User**: Your question
2. **System**: 🔧 "Analyzing request and selecting appropriate tools..."
3. **System**: 🔧 "Calling Tool: browser_navigate"
4. **System**: ✅ "Tool execution completed successfully"
5. **Assistant**: Comprehensive response with extracted information

### 🔧 Troubleshooting

#### WebSocket Connection Issues
- **Problem**: "Not Found: /ws/chat/" errors
- **Solution**: Make sure you're using `daphne` (ASGI) not `python manage.py runserver` (WSGI)

#### Agent Mode Not Working
- **Check**: MCP server is running on port 9000
- **Check**: Agent Mode checkbox is enabled
- **Check**: Backend logs show tool calling activity

#### Desktop App Won't Connect
- **Check**: All three services are running
- **Check**: No firewall blocking ports 8000 or 9000
- **Check**: Backend shows WebSocket connection logs

### 🔑 Environment Variables
Create `Main/backend/.env` with:
```
API_KEY7=your_openai_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

## Key Features

1. **Independent Desktop Application**: FinGPT-desktop provides a standalone chat interface that automatically opens on startup
2. **Smart Page Context**: Chrome extension automatically collects and analyzes current webpage content
3. **Real-time Streaming**: Ultra-fast 2ms streaming responses with complete Markdown rendering
4. **Multi-Model Support**: Compatible with OpenAI, DeepSeek, and Anthropic models
5. **Advanced RAG**: Dedicated retrieval system for local files (SEC 10K, XBRL files)
6. **Source Verification**: Users can check the sources of generated responses, ensuring reliability and accuracy

**NO Trading Suggestions!**

## Architecture

The system consists of three main components:

1. **FinGPT-desktop**: Electron-based desktop application providing the main chat interface
2. **Chrome Extension**: Collects webpage content and manages browser integration
3. **Django Backend**: Handles AI model interactions, WebSocket connections, and context management

### Project Structure

```
FinGPT-Search-Agent/
├── FinGPT-desktop/          # Electron desktop application
│   ├── main.js              # Main process
│   ├── renderer.html        # UI layout
│   └── renderer.js          # Renderer process with WebSocket client
├── Main/
│   ├── backend/             # Django backend server
│   │   ├── api/             # WebSocket consumers and views
│   │   ├── datascraper/     # RAG and model configuration
│   │   └── django_config/   # Django settings and routing
│   └── frontend/            # Chrome extension
│       ├── src/             # Extension source code
│       └── dist/            # Built extension files
├── scripts/                 # Installation and setup scripts
└── Requirements/            # Platform-specific requirements
```

### Current Progress

1. **Independent Desktop Chat**: FinGPT-desktop provides a standalone chat interface with Markdown rendering
   ![image](Docs/source/_static/images/F4.0_1.png)

2. **Source Verification**: Check sources of generated responses to reduce misinformation
   ![image](Docs/source/_static/images/F4.0_Source.png)

3. **Advanced RAG System**: Dedicated retrieval for local files (SEC 10K, XBRL files)
   ![image](Docs/source/_static/images/F4.0_RAG_1.png)


## Installation

### Prerequisites

- **Python 3.10+** 
- **Node.js 18+**
- **Google Chrome** browser

### Quick Install

#### All Platforms

```bash
# Clone the repository
git clone https://github.com/Open-Finance-Lab/FinGPT-Search-Agent.git
cd FinGPT-Search-Agent

# Run the unified installer
python scripts/install_all.py  # Windows
python3 scripts/install_all.py # Mac/Linux
```

#### Alternative Methods

**Using Make (Mac/Linux):**
```bash
make install
make dev  # Start development servers
```

**Using PowerShell (Windows):**
```powershell
.\make.ps1 install
.\make.ps1 dev  # Start development servers
```

### Post-Installation

1. **Configure API Keys (Required)**
   
   The installer will prompt you to add API keys. Edit `Main/backend/.env` and add at least one:
   ```
   OPENAI_API_KEY=your-actual-openai-key
   ANTHROPIC_API_KEY=your-actual-anthropic-key
   DEEPSEEK_API_KEY=your-actual-deepseek-key
   ```
   
   **Note**: The server will refuse to start without at least one valid API key configured.

2. **Load Browser Extension**
   
   - Open Chrome and navigate to Extensions page → `chrome://extensions`
   - Enable Developer mode
   - Click "Load unpacked"
   - Select `Main/frontend/dist` folder

3. **Start Development Server**

   ```bash
   python scripts/dev_setup.py  # Windows
   python3 scripts/dev_setup.py # Mac/Linux
   ```

4. **Launch FinGPT Desktop Application**

   ```bash
   cd FinGPT-desktop
   npm start
   ```

   The desktop application will automatically open and connect to the backend server.

### Troubleshooting

- **"No API keys configured!"**: The server won't start without valid API keys in `.env`
- **Virtual Environment**: The installer creates `FinGPTenv`. Activate it before running servers.
- **Port 8000 in use**: Close other servers or continue anyway.
- **Non-English systems**: UTF-8 encoding is automatically handled.

## Usage

### Quick Start

1. **Start the Backend Server**: Run `python scripts/dev_setup.py`
2. **Launch FinGPT-desktop**: Run `cd FinGPT-desktop && npm start`
3. **Load Chrome Extension**: Load `Main/frontend/dist` as unpacked extension
4. **Start Chatting**: The desktop app opens automatically and connects to your current webpage context

### Key Features in Action

- **Smart Context**: Browse any webpage, and FinGPT automatically understands the content
- **Streaming Responses**: Get real-time AI responses with 2ms streaming delay
- **Markdown Support**: Responses display with proper formatting (headers, lists, code blocks)
- **Multi-Model**: Switch between GPT, Claude, and DeepSeek models
- **Source Verification**: Check where information comes from

## Documentation

For detailed usage instructions and more information, see: https://fingpt-search-agent-docs.readthedocs.io/

## Roadmap

### Immediate Next Steps
1. Deploy the backend to cloud for simplified installation
2. Add more financial data sources and APIs

### Future Plans
1. Zero-knowledge proof (ZKP) demo for privacy-preserving financial analysis
2. Advanced portfolio analysis tools
3. Real-time market data integration

Citing:

```
@inproceedings{tian2024customized,
  title={Customized fingpt search agents using foundation models},
  author={Tian, Felix and Byadgi, Ajay and Kim, Daniel S and Zha, Daochen and White, Matt and Xiao, Kairong and Liu, Xiao-Yang},
  booktitle={Proceedings of the 5th ACM International Conference on AI in Finance},
  pages={469--477},
  year={2024}
}
```


**Disclaimer: We are sharing codes for academic purposes under the MIT education license. Nothing herein is financial 
advice, and NOT a recommendation to trade real money. Please use common sense and always first consult a professional
before trading or investing.**
