// content.js - WebSocket Content Script for FinGPT
class FinGPTContentScript {
    constructor() {
        this.ws = null;
        this.sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        this.isConnected = false;
        this.currentUrl = window.location.href;
        this.lastContent = '';

        this.init();
    }

    init() {
        console.log('FinGPT Content Script initialized');
        console.log('Session ID:', this.sessionId);
        console.log('Current URL:', this.currentUrl);

        this.connectWebSocket();
        this.setupMessageListener();
        // 恢复定时获取模式
        this.setupPageObserver();
        this.sendInitialPageInfo();
        this.setupVisibilityListener();
        this.startPeriodicUpdate();
    }

    connectWebSocket() {
        try {
            this.ws = new WebSocket('ws://localhost:8000/ws/page_info/');

            this.ws.onopen = () => {
                console.log('Page info WebSocket connected');
                this.isConnected = true;
                this.reportConnectionStatus();
            };

            this.ws.onclose = () => {
                console.log('Page info WebSocket disconnected');
                this.isConnected = false;
                this.reportConnectionStatus();
                // Attempt to reconnect after 3 seconds
                setTimeout(() => this.connectWebSocket(), 3000);
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };

            this.ws.onerror = (error) => {
                console.error('Page info WebSocket error:', error);
            };

        } catch (error) {
            console.error('Failed to create page info WebSocket:', error);
        }
    }

    handleWebSocketMessage(data) {
        console.log('Content Script: Received WebSocket message:', data);

        if (data.type === 'request_page_info') {
            console.log('Content Script: Received page info request, sending response...');
            // 响应页面信息请求
            this.sendCurrentPageInfo();
        } else {
            console.log('Content Script: Unknown message type:', data.type);
        }
    }

    sendCurrentPageInfo() {
        if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }

        const textContent = document.body.innerText || '';
        const pageTitle = document.title || '';
        const isActive = !document.hidden;

        const message = {
            type: 'page_info_response',
            url: this.currentUrl,
            content: textContent,
            title: pageTitle,
            session_id: this.sessionId,
            timestamp: Date.now(),
            is_active: isActive
        };

        this.ws.send(JSON.stringify(message));
        console.log(`Content Script: Current page info sent: ${pageTitle} (${isActive ? 'active' : 'background'})`);
        console.log('Content Script: Message sent:', message);
    }

    startPeriodicUpdate() {
        // 每30秒发送一次页面信息更新
        this.updateInterval = setInterval(() => {
            if (this.isConnected) {
                this.sendPageUpdate();
            }
        }, 30000); // 30秒间隔

        console.log('Started periodic page updates (30s interval)');
    }

    sendPageUpdate() {
        if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }

        const textContent = document.body.innerText || '';
        const pageTitle = document.title || '';
        const isActive = !document.hidden;

        const message = {
            type: 'page_update',
            url: this.currentUrl,
            content: textContent,
            title: pageTitle,
            session_id: this.sessionId,
            timestamp: Date.now(),
            is_active: isActive
        };

        this.ws.send(JSON.stringify(message));
        console.log(`Periodic update sent: ${pageTitle} (${isActive ? 'active' : 'background'})`);
    }

    sendPageUpdate(content = null) {
        if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }

        const textContent = content || document.body.innerText || '';

        // Only send if content has changed significantly
        if (textContent === this.lastContent) {
            return;
        }

        this.lastContent = textContent;

        // 获取页面标题
        const pageTitle = document.title || '';

        // 检测是否为活跃页面（当前标签页是否可见）
        const isActive = !document.hidden;

        const message = {
            type: 'page_update',
            url: this.currentUrl,
            content: textContent,
            title: pageTitle,
            session_id: this.sessionId,
            timestamp: Date.now(),
            is_active: isActive
        };

        this.ws.send(JSON.stringify(message));
        console.log(`Page info sent to WebSocket (${isActive ? 'active' : 'background'}): ${pageTitle}`);
    }

    sendInitialPageInfo() {
        // Send initial page content
        this.sendPageUpdate();
    }

    setupPageObserver() {
        // Watch for URL changes (SPA navigation)
        let lastUrl = this.currentUrl;
        const urlObserver = new MutationObserver(() => {
            if (window.location.href !== lastUrl) {
                lastUrl = window.location.href;
                this.currentUrl = lastUrl;
                console.log('URL changed to:', this.currentUrl);
                this.sendPageUpdate();
            }
        });

        urlObserver.observe(document, { subtree: true, childList: true });

        // Watch for significant content changes
        const contentObserver = new MutationObserver((mutations) => {
            let shouldUpdate = false;

            mutations.forEach((mutation) => {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    // Check if added nodes contain significant text content
                    for (let node of mutation.addedNodes) {
                        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 10) {
                            shouldUpdate = true;
                            break;
                        } else if (node.nodeType === Node.ELEMENT_NODE && node.innerText && node.innerText.trim().length > 10) {
                            shouldUpdate = true;
                            break;
                        }
                    }
                }
            });

            if (shouldUpdate) {
                // Debounce updates
                clearTimeout(this.updateTimeout);
                this.updateTimeout = setTimeout(() => {
                    this.sendPageUpdate();
                }, 1000);
            }
        });

        contentObserver.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true
        });
    }

    setupMessageListener() {
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            switch (message.type) {
                case 'CONNECT':
                    this.connectWebSocket();
                    sendResponse({ success: true });
                    break;
                case 'DISCONNECT':
                    this.disconnect();
                    sendResponse({ success: true });
                    break;
                default:
                    sendResponse({ success: false, error: 'Unknown message type' });
            }
            return true;
        });
    }

    setupVisibilityListener() {
        // 监听页面可见性变化
        document.addEventListener('visibilitychange', () => {
            // 当页面可见性变化时，发送更新
            if (this.isConnected) {
                this.sendPageUpdate();
            }
        });
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
        this.reportConnectionStatus();
    }

    reportConnectionStatus() {
        const status = {
            connected: this.isConnected,
            sessionId: this.sessionId,
            url: this.currentUrl,
            timestamp: Date.now()
        };

        chrome.runtime.sendMessage({
            type: 'CONNECTION_STATUS_CHANGED',
            status: status
        }).catch(() => {
            // Background script might not be ready, that's okay
        });
    }
}

// Prevent multiple injections
if (window.fingptInjected) {
    console.log('FinGPT already injected on this page');
} else {
    window.fingptInjected = true;

    // Initialize content script
    new FinGPTContentScript();

    console.log('FinGPT WebSocket content script initialized');
}


