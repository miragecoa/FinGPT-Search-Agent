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
                this.currentStreamMessage = this.addMessage('assistant', '', true); // 创建空的助手消息
                console.log('Stream started with model:', data.model);
                break;

            case 'stream_content':
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
                break;

            case 'response_complete':
                if (data.r2c_stats) {
                    console.log('R2C Stats:', data.r2c_stats);
                }
                console.log('Response completed with model:', data.model);
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
                break;

            case 'error':
                this.showLoading(false);
                this.showStatus('');
                this.addMessage('system', `Error: ${data.message}`);
                break;

            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;
        
        // Add user message to chat
        this.addMessage('user', message);
        
        // Clear input
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        
        // Send to WebSocket
        this.sendWebSocketMessage({
            type: 'chat_message',
            message: message,
            models: [this.modelSelect.value],
            use_rag: this.ragCheckbox.checked
        });
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
