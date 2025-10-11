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
        this.setupBrowserControlListener();  // 新增：监听浏览器控制命令
        // 恢复定时获取模式
        this.setupPageObserver();
        this.setupPageLoadListener();  // 新增：监听页面加载事件
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

        // 确保使用最新的URL
        this.currentUrl = window.location.href;

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
        console.log(`Content Script: Current page info sent: ${pageTitle} (${isActive ? 'active' : 'background'}) - URL: ${this.currentUrl}`);
        console.log('Content Script: Message sent:', message);
    }

    startPeriodicUpdate() {
        // 每5秒发送一次页面信息更新
        this.updateInterval = setInterval(() => {
            if (this.isConnected) {
                this.sendPageUpdate();
            }
        }, 5000); // 5秒间隔

        console.log('Started periodic page updates (30s interval)');
    }

    sendPageUpdate() {
        if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }

        // 确保使用最新的URL
        this.currentUrl = window.location.href;

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
        console.log(`Periodic update sent: ${pageTitle} (${isActive ? 'active' : 'background'}) - URL: ${this.currentUrl}`);
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

        // 确保使用最新的URL
        this.currentUrl = window.location.href;

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
        console.log(`Page info sent to WebSocket (${isActive ? 'active' : 'background'}): ${pageTitle} - URL: ${this.currentUrl}`);
    }

    sendInitialPageInfo() {
        // Send initial page content
        this.sendPageUpdate();
    }

    sendPageNavigationSignal() {
        if (!this.isConnected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }

        // 确保使用最新的URL
        this.currentUrl = window.location.href;

        const message = {
            type: 'page_navigation',
            url: this.currentUrl,
            title: document.title || '',
            session_id: this.sessionId,
            timestamp: Date.now(),
            message: 'Page navigation detected'
        };

        this.ws.send(JSON.stringify(message));
        console.log(`Content Script: Page navigation signal sent: ${this.currentUrl}`);
    }

    setupPageObserver() {
        // Watch for URL changes (SPA navigation)
        let lastUrl = this.currentUrl;
        const urlObserver = new MutationObserver(() => {
            if (window.location.href !== lastUrl) {
                lastUrl = window.location.href;
                this.currentUrl = lastUrl;
                console.log('URL changed to:', this.currentUrl);

                // 发送页面切换信号
                this.sendPageNavigationSignal();

                // 延迟发送页面更新，确保页面内容已加载
                setTimeout(() => {
                    this.sendPageUpdate();
                }, 2000);
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

    setupPageLoadListener() {
        // 监听页面加载完成事件
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                console.log('DOMContentLoaded - sending page info');
                setTimeout(() => this.sendPageUpdate(), 1000); // 延迟1秒确保页面完全加载
            });
        }

        window.addEventListener('load', () => {
            console.log('Window load - sending page info');
            setTimeout(() => this.sendPageUpdate(), 2000); // 延迟2秒确保所有资源加载完成
        });

        // 监听popstate事件（浏览器前进后退）
        window.addEventListener('popstate', () => {
            console.log('Popstate event - URL changed');
            setTimeout(() => {
                this.currentUrl = window.location.href;
                this.sendPageUpdate();
            }, 500);
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

    // 设置浏览器控制监听器，接收来自background script的命令
    setupBrowserControlListener() {
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            console.log('Content script received message:', message);

            switch (message.type) {
                case 'press_key':
                    this.handlePressKey(message.key);
                    sendResponse({ success: true });
                    break;
                case 'type_text':
                    this.handleTypeText(message.text);
                    sendResponse({ success: true });
                    break;
                case 'click_element':
                    this.handleClickElement(message.selector);
                    sendResponse({ success: true });
                    break;
                case 'get_page_info':
                    const pageInfo = this.getPageInfo();
                    sendResponse(pageInfo);
                    break;
                default:
                    console.log('Unknown message type:', message.type);
                    sendResponse({ success: false, error: 'Unknown message type' });
            }

            return true; // 保持消息通道开放
        });
    }

    // 处理按键操作
    handlePressKey(key) {
        try {
            // 获取当前焦点元素
            const activeElement = document.activeElement;

            // 创建键盘事件
            const keyEvent = new KeyboardEvent('keydown', {
                key: key,
                code: this.getKeyCode(key),
                bubbles: true,
                cancelable: true
            });

            // 如果有焦点元素，向其发送事件，否则向document发送
            const target = activeElement || document;
            target.dispatchEvent(keyEvent);

            // 也发送keyup事件
            const keyUpEvent = new KeyboardEvent('keyup', {
                key: key,
                code: this.getKeyCode(key),
                bubbles: true,
                cancelable: true
            });
            target.dispatchEvent(keyUpEvent);

            console.log(`Pressed key: ${key}`);
        } catch (error) {
            console.error('Error pressing key:', error);
        }
    }

    // 处理文本输入操作
    handleTypeText(text) {
        try {
            // 获取当前焦点元素
            const activeElement = document.activeElement;

            if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA' || activeElement.contentEditable === 'true')) {
                // 如果是输入框或可编辑元素，直接设置值
                if (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA') {
                    activeElement.value = text;
                    // 触发input事件
                    activeElement.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    // 对于contentEditable元素
                    activeElement.textContent = text;
                }

                console.log(`Typed text: ${text}`);
            } else {
                // 如果没有焦点元素，尝试找到第一个输入框
                const inputElement = document.querySelector('input[type="text"], input[type="search"], textarea');
                if (inputElement) {
                    inputElement.focus();
                    inputElement.value = text;
                    inputElement.dispatchEvent(new Event('input', { bubbles: true }));
                    console.log(`Typed text in found input: ${text}`);
                } else {
                    console.warn('No suitable input element found for typing');
                }
            }
        } catch (error) {
            console.error('Error typing text:', error);
        }
    }

    // 获取键码映射
    getKeyCode(key) {
        const keyCodeMap = {
            'Enter': 'Enter',
            'Tab': 'Tab',
            'Escape': 'Escape',
            'Space': 'Space',
            'ArrowUp': 'ArrowUp',
            'ArrowDown': 'ArrowDown',
            'ArrowLeft': 'ArrowLeft',
            'ArrowRight': 'ArrowRight',
            'Backspace': 'Backspace',
            'Delete': 'Delete'
        };

        return keyCodeMap[key] || key;
    }

    // 处理点击操作
    handleClickElement(selector) {
        try {
            // 使用CSS选择器查找元素
            const element = document.querySelector(selector);

            if (element) {
                // 创建点击事件
                const clickEvent = new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });

                // 触发点击事件
                element.dispatchEvent(clickEvent);

                // 也可以直接调用click方法
                element.click();

                console.log(`Clicked element with selector: ${selector}`);
            } else {
                console.warn(`Element not found with selector: ${selector}`);
            }
        } catch (error) {
            console.error('Error clicking element:', error);
        }
    }

    // 获取当前页面信息
    getPageInfo() {
        try {
            console.log('getPageInfo called, document ready state:', document.readyState);

            const title = document.title || 'Unknown Title';
            const url = window.location.href;

            console.log('Page title:', title);
            console.log('Page URL:', url);

            // 获取页面主要内容
            let content = '';
            let foundSelector = 'none';

            // 尝试获取主要内容区域
            const mainSelectors = [
                'main',
                '[role="main"]',
                '.main-content',
                '#main-content',
                '.content',
                '#content',
                'article',
                '.article'
            ];

            let mainElement = null;
            for (const selector of mainSelectors) {
                mainElement = document.querySelector(selector);
                if (mainElement) {
                    foundSelector = selector;
                    break;
                }
            }

            if (mainElement) {
                content = mainElement.innerText || mainElement.textContent || '';
                console.log(`Found content using selector: ${foundSelector}, length: ${content.length}`);
            } else {
                // 如果没找到主要内容区域，获取body内容
                if (document.body) {
                    content = document.body.innerText || document.body.textContent || '';
                    foundSelector = 'body';
                    console.log(`Using body content, length: ${content.length}`);
                } else {
                    console.log('No body element found');
                }
            }

            // 清理和截断内容
            content = content.replace(/\s+/g, ' ').trim();
            if (content.length > 5000) {
                content = content.substring(0, 5000) + '...';
            }

            const result = {
                title: title,
                url: url,
                content: content,
                timestamp: new Date().toISOString(),
                debug: {
                    readyState: document.readyState,
                    foundSelector: foundSelector,
                    originalContentLength: content.length
                }
            };

            console.log('getPageInfo result:', result);
            return result;

        } catch (error) {
            console.error('Error getting page info:', error);
            return {
                title: 'Error',
                url: window.location.href || 'Unknown URL',
                content: 'Failed to extract page content',
                error: error.message,
                timestamp: new Date().toISOString()
            };
        }
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


