const { ipcRenderer } = require('electron');

class FinGPTClient {
    constructor() {
        this.ws = null;
        this.sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        this.isConnected = false;
        this.messageQueue = [];
        
        this.initializeElements();
        this.setupEventListeners();
        this.connectWebSocket();
    }
    
    initializeElements() {
        this.chatArea = document.getElementById('chatArea');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.settingsBtn = document.getElementById('settingsBtn');
        this.modelSelect = document.getElementById('modelSelect');
        this.ragCheckbox = document.getElementById('ragCheckbox');
        this.agentCheckbox = document.getElementById('agentCheckbox');
        this.status = document.getElementById('status');
        this.loading = document.getElementById('loading');
    }
    
    setupEventListeners() {
        // Send button
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        
        // Enter key to send
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Auto-resize textarea
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 100) + 'px';
        });
        
        // Clear chat
        this.clearBtn.addEventListener('click', () => this.clearChat());
        
        // Settings (placeholder)
        this.settingsBtn.addEventListener('click', () => {
            alert('Settings panel coming soon!');
        });
    }
    
    connectWebSocket() {
        try {
            this.ws = new WebSocket('ws://localhost:8000/ws/chat/');
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.updateStatus('Connected', 'connected');
                
                // Set session ID
                this.sendWebSocketMessage({
                    type: 'set_session',
                    session_id: this.sessionId
                });
                
                // Process queued messages
                this.processMessageQueue();
            };
            
            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.isConnected = false;
                this.updateStatus('Disconnected', 'disconnected');
                
                // Attempt to reconnect after 3 seconds
                setTimeout(() => this.connectWebSocket(), 3000);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateStatus('Connection Error', 'disconnected');
            };
            
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.updateStatus('Connection Failed', 'disconnected');
        }
    }
    
    sendWebSocketMessage(message) {
        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            this.messageQueue.push(message);
        }
    }
    
    processMessageQueue() {
        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            this.sendWebSocketMessage(message);
        }
    }
    
    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'session_set':
                console.log('Session set:', data.session_id);
                break;

            case 'status':
                this.showStatus(data.message);
                break;

            case 'stream_start':
                this.showLoading(false);
                // 不在这里创建消息泡泡，等到真正的stream_chunk时再创建
                console.log('Stream started with model:', data.model);
                break;

            case 'stream_content':
                if (this.currentStreamMessage) {
                    this.appendToMessage(this.currentStreamMessage, data.content);
                }
                break;

            case 'stream_chunk':
                // Agent模式下的流式数据 - 总是为最终回复创建新的消息泡泡
                if (!this.currentStreamMessage) {
                    // 创建新的消息泡泡用于最终回复（在工具调用之后）
                    this.currentStreamMessage = this.addMessage('assistant', '', true);
                    this.showLoading(false);
                    console.log('Created new stream message bubble for final response at:', new Date().toLocaleTimeString());
                }
                if (this.currentStreamMessage) {
                    this.appendToMessage(this.currentStreamMessage, data.content);
                }
                break;

            case 'stream_end':
                if (this.currentStreamMessage) {
                    // 流式结束时渲染Markdown
                    const streamContent = this.currentStreamMessage.querySelector('.stream-content');
                    if (streamContent) {
                        this.renderMarkdown(streamContent);
                    }
                }
                this.currentStreamMessage = null;
                this.showStatus('');
                // Reset send button when stream ends
                this.setSendButtonState('send');
                break;

            case 'response_complete':
                if (data.r2c_stats) {
                    console.log('R2C Stats:', data.r2c_stats);
                }
                console.log('Response completed with model:', data.model);
                // Reset send button when response completes
                this.setSendButtonState('send');
                break;

            case 'processing':
                this.showLoading(true);
                break;

            case 'chat_response':
                // 兼容旧的非流式响应
                this.showLoading(false);
                this.addMessage('assistant', data.message);
                if (data.r2c_stats) {
                    console.log('R2C Stats:', data.r2c_stats);
                }
                // Reset send button for non-stream responses
                this.setSendButtonState('send');
                break;

            case 'tool_calling':
                // 显示工具调用状态
                this.addToolMessage('calling', data.message, data.tool_details);
                break;

            case 'tool_result':
                // 显示工具执行结果
                this.addToolMessage('result', data.message, data.tool_details);
                break;

            case 'error':
                this.showLoading(false);
                this.showStatus('');
                this.addMessage('system', `Error: ${data.message}`);
                // Reset send button on error
                this.setSendButtonState('send');
                break;

            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    sendMessage() {
        // Check if we're in stop mode
        if (this.sendBtn.textContent === 'Stop') {
            this.stopGeneration();
            return;
        }

        const message = this.messageInput.value.trim();
        if (!message) return;

        // Add user message to chat
        this.addMessage('user', message);

        // Clear input
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        // Change button to Stop
        this.setSendButtonState('stop');

        // Send to WebSocket
        this.sendWebSocketMessage({
            type: 'chat_message',
            message: message,
            models: [this.modelSelect.value],
            use_rag: this.ragCheckbox.checked,
            use_agent: this.agentCheckbox.checked
        });
    }

    stopGeneration() {
        // Send stop signal to backend
        this.sendWebSocketMessage({
            type: 'stop_generation'
        });

        // Reset button state
        this.setSendButtonState('send');

        // Add stop message to chat
        this.addMessage('system', '⏹️ Generation stopped by user');
    }

    setSendButtonState(state) {
        if (state === 'stop') {
            this.sendBtn.textContent = 'Stop';
            this.sendBtn.style.backgroundColor = '#dc3545';
        } else {
            this.sendBtn.textContent = 'Send';
            this.sendBtn.style.backgroundColor = '#007bff';
        }
    }
    
    addMessage(role, content, isStream = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}-message`;

        if (isStream) {
            // 为流式消息创建一个可以追加内容的容器
            messageDiv.innerHTML = '<span class="stream-content"></span>';
        } else {
            messageDiv.textContent = content;
        }

        // Remove welcome message if it exists
        const welcome = this.chatArea.querySelector('.welcome');
        if (welcome) {
            welcome.remove();
        }

        this.chatArea.appendChild(messageDiv);
        this.chatArea.scrollTop = this.chatArea.scrollHeight;

        // 返回消息元素以便流式更新
        return messageDiv;
    }

    addToolMessage(type, message, toolDetails = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message system-message tool-message`;

        const toolHeader = document.createElement('div');
        toolHeader.className = 'tool-header';

        const icon = type === 'calling' ? '🔧' : '✅';
        const headerText = document.createElement('span');
        headerText.textContent = `${icon} ${message}`;

        toolHeader.appendChild(headerText);

        // 如果有工具详情，添加展开按钮
        if (toolDetails) {
            const expandButton = document.createElement('button');
            expandButton.className = 'tool-expand-btn';
            expandButton.textContent = '▼';
            expandButton.onclick = () => this.toggleToolDetails(expandButton, toolDetails);
            toolHeader.appendChild(expandButton);

            // 创建详情容器（初始隐藏）
            const detailsDiv = document.createElement('div');
            detailsDiv.className = 'tool-details hidden';

            const detailsContent = document.createElement('pre');
            detailsContent.textContent = JSON.stringify(toolDetails, null, 2);
            detailsDiv.appendChild(detailsContent);

            messageDiv.appendChild(toolHeader);
            messageDiv.appendChild(detailsDiv);
        } else {
            messageDiv.appendChild(toolHeader);
        }

        // Remove welcome message if it exists
        const welcome = this.chatArea.querySelector('.welcome');
        if (welcome) {
            welcome.remove();
        }

        this.chatArea.appendChild(messageDiv);
        this.chatArea.scrollTop = this.chatArea.scrollHeight;
    }

    toggleToolDetails(button, toolDetails) {
        const messageDiv = button.closest('.tool-message');
        const detailsDiv = messageDiv.querySelector('.tool-details');

        if (detailsDiv.classList.contains('hidden')) {
            detailsDiv.classList.remove('hidden');
            button.textContent = '▲';
        } else {
            detailsDiv.classList.add('hidden');
            button.textContent = '▼';
        }
    }

    appendToMessage(messageElement, content) {
        const streamContent = messageElement.querySelector('.stream-content');
        if (streamContent) {
            streamContent.textContent += content;
        } else {
            messageElement.textContent += content;
        }
        this.chatArea.scrollTop = this.chatArea.scrollHeight;
    }

    renderMarkdown(element) {
        const text = element.textContent;

        // 分行处理，保持段落结构
        const lines = text.split('\n');
        let html = '';
        let inList = false;
        let listItems = [];

        for (let i = 0; i < lines.length; i++) {
            let line = lines[i].trim();

            // 处理列表项
            if (line.match(/^- /)) {
                if (!inList) {
                    inList = true;
                    listItems = [];
                }
                listItems.push(line.replace(/^- /, ''));
                continue;
            } else if (line.match(/^\d+\. /)) {
                if (!inList) {
                    inList = true;
                    listItems = [];
                }
                listItems.push(line.replace(/^\d+\. /, ''));
                continue;
            } else {
                // 如果之前在处理列表，现在结束列表
                if (inList) {
                    html += '<ul>';
                    listItems.forEach(item => {
                        html += `<li>${this.processInlineMarkdown(item)}</li>`;
                    });
                    html += '</ul>';
                    inList = false;
                    listItems = [];
                }
            }

            // 处理标题
            if (line.match(/^### /)) {
                html += `<h3>${this.processInlineMarkdown(line.replace(/^### /, ''))}</h3>`;
            } else if (line.match(/^## /)) {
                html += `<h2>${this.processInlineMarkdown(line.replace(/^## /, ''))}</h2>`;
            } else if (line.match(/^# /)) {
                html += `<h1>${this.processInlineMarkdown(line.replace(/^# /, ''))}</h1>`;
            } else if (line.length > 0) {
                // 普通段落
                html += `<p>${this.processInlineMarkdown(line)}</p>`;
            } else {
                // 空行
                html += '<br>';
            }
        }

        // 处理最后的列表
        if (inList) {
            html += '<ul>';
            listItems.forEach(item => {
                html += `<li>${this.processInlineMarkdown(item)}</li>`;
            });
            html += '</ul>';
        }

        element.innerHTML = html;
    }

    processInlineMarkdown(text) {
        return text
            // 粗体 **text**
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            // 斜体 *text* (但不影响已处理的粗体)
            .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
            // 代码块 `code`
            .replace(/`([^`]+)`/g, '<code>$1</code>');
    }



    showStatus(message) {
        if (message) {
            this.status.textContent = message;
            this.status.style.display = 'block';
        } else {
            this.status.style.display = 'none';
        }
    }
    
    clearChat() {
        this.chatArea.innerHTML = `
            <div class="welcome">
                Welcome to FinGPT Assistant!<br>
                Ask me anything about finance or the current page.
            </div>
        `;
    }
    
    showLoading(show) {
        if (show) {
            this.loading.classList.add('show');
            this.sendBtn.disabled = true;
        } else {
            this.loading.classList.remove('show');
            this.sendBtn.disabled = false;
        }
    }
    
    updateStatus(message, className) {
        this.status.textContent = message;
        this.status.className = `status ${className}`;
    }
}

// Initialize the client when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new FinGPTClient();
});
