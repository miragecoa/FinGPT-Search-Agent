// background.js - Service Worker for FinGPT WebSocket

class FinGPTBackground {
    constructor() {
        this.connectionStates = new Map(); // tabId -> connection state
        this.websocket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.connectToBackend();
        console.log('FinGPT WebSocket background service worker initialized');
    }

    setupEventListeners() {
        // Handle extension installation
        chrome.runtime.onInstalled.addListener((details) => {
            this.handleInstallation(details);
        });

        // Handle messages from content scripts
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            this.handleMessage(message, sender, sendResponse);
            return true; // Keep message channel open for async responses
        });

        // Handle tab updates to inject content script if needed
        chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
            this.handleTabUpdate(tabId, changeInfo, tab);
        });

        // Handle browser action click - launch Electron app
        chrome.action.onClicked.addListener((tab) => {
            this.handleActionClick(tab);
        });
    }

    handleInstallation(details) {
        console.log('FinGPT WebSocket installed:', details.reason);

        if (details.reason === 'install') {
            // Set default settings on first install
            chrome.storage.local.set({
                fingptSettings: {
                    websocketEndpoint: 'ws://localhost:8000/ws/',
                    backendEndpoint: 'http://127.0.0.1:8000',
                    electronAppPath: null
                }
            });

            // Show notification about Electron app
            chrome.notifications.create({
                type: 'basic',
                iconUrl: 'icon48.png',
                title: 'FinGPT Assistant',
                message: 'Please start the FinGPT Desktop app to use the assistant.'
            });
            chrome.tabs.create({
                url: chrome.runtime.getURL('popup.html')
            });
        }
    }

    async handleMessage(message, sender, sendResponse) {
        try {
            switch (message.type) {
                case 'GET_PAGE_CONTENT':
                    const pageContent = await this.getPageContent(sender.tab.id);
                    sendResponse({ success: true, data: pageContent });
                    break;

                case 'INJECT_CONTENT_SCRIPT':
                    await this.injectContentScript(message.tabId);
                    sendResponse({ success: true });
                    break;

                case 'CHECK_MCP_STATUS':
                    const mcpStatus = await this.checkMCPStatus();
                    sendResponse({ success: true, data: mcpStatus });
                    break;

                case 'GET_CONNECTION_STATUS':
                    // For popup requests, get the active tab
                    const activeTab = await this.getActiveTab();
                    const tabId = sender.tab ? sender.tab.id : (activeTab ? activeTab.id : null);
                    const status = this.getConnectionStatus(tabId);
                    sendResponse({ success: true, data: status });
                    break;

                case 'SET_CONNECTION_STATUS':
                    // For popup requests, get the active tab
                    const activeTabForSet = await this.getActiveTab();
                    const targetTabId = sender.tab ? sender.tab.id : (activeTabForSet ? activeTabForSet.id : null);
                    if (targetTabId) {
                        await this.setConnectionStatus(targetTabId, message.connected);
                        sendResponse({ success: true });
                    } else {
                        sendResponse({ success: false, error: 'No active tab found' });
                    }
                    break;

                case 'CONNECTION_STATUS_CHANGED':
                    this.updateConnectionStatus(sender.tab.id, message.status);
                    this.notifyPopupStatusChange(sender.tab.id, message.status);
                    sendResponse({ success: true });
                    break;

                case 'PING':
                    sendResponse({ success: true, message: 'pong' });
                    break;

                default:
                    sendResponse({ success: false, error: 'Unknown message type' });
            }
        } catch (error) {
            console.error('Error handling message:', error);
            sendResponse({ success: false, error: error.message });
        }
    }

    handleTabUpdate(tabId, changeInfo, tab) {
        // Only process when page is completely loaded
        if (changeInfo.status !== 'complete') return;
        
        // Skip chrome:// and extension pages
        if (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
            return;
        }

        // Inject content script if needed
        this.ensureContentScriptInjected(tabId);
    }

    async handleActionClick(tab) {
        // Show notification to remind user to use Electron app
        chrome.notifications.create({
            type: 'basic',
            iconUrl: 'icon48.png',
            title: 'FinGPT Assistant',
            message: 'Please use the FinGPT Desktop app for chatting. Use Ctrl+Shift+F to toggle it.'
        });

        console.log('Extension icon clicked - user reminded to use desktop app');
    }

    async getPageContent(tabId) {
        try {
            const results = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                function: () => {
                    return {
                        title: document.title,
                        url: window.location.href,
                        content: document.body.innerText || document.body.textContent || '',
                        html: document.documentElement.outerHTML,
                        timestamp: Date.now()
                    };
                }
            });

            return results[0].result;
        } catch (error) {
            console.error('Error getting page content:', error);
            throw new Error('Unable to access page content');
        }
    }

    async injectContentScript(tabId) {
        try {
            // Check if content script is already injected
            const results = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                function: () => {
                    return window.fingptInjected || false;
                }
            });

            if (results[0].result) {
                console.log('Content script already injected');
                return;
            }

            // Inject the content script
            await chrome.scripting.executeScript({
                target: { tabId: tabId },
                files: ['vendors.js', 'katex.js', 'content.js']
            });

            await chrome.scripting.insertCSS({
                target: { tabId: tabId },
                files: ['styles.css']
            });

            console.log('Content script injected successfully');
        } catch (error) {
            console.error('Error injecting content script:', error);
            throw error;
        }
    }

    async ensureContentScriptInjected(tabId) {
        try {
            // Get settings to check if auto-injection is enabled
            const result = await chrome.storage.local.get('fingptSettings');
            const settings = result.fingptSettings || {};

            // Only auto-inject if enabled in settings
            if (settings.autoInject !== false) { // Default to true
                await this.injectContentScript(tabId);
            }
        } catch (error) {
            console.error('Error ensuring content script injection:', error);
        }
    }

    async checkMCPStatus() {
        try {
            const settings = await chrome.storage.local.get('fingptSettings');
            const apiEndpoint = settings.fingptSettings?.apiEndpoint || 'http://127.0.0.1:8000';

            const response = await fetch(`${apiEndpoint}/api/mcp_servers/`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            return {
                connected: true,
                servers: data.servers || [],
                totalTools: data.servers?.reduce((sum, server) => sum + (server.tools_count || 0), 0) || 0
            };
        } catch (error) {
            return {
                connected: false,
                error: error.message,
                servers: [],
                totalTools: 0
            };
        }
    }

    // Utility method to send messages to content scripts
    async sendMessageToTab(tabId, message) {
        try {
            return await chrome.tabs.sendMessage(tabId, message);
        } catch (error) {
            console.error('Error sending message to tab:', error);
            throw error;
        }
    }

    // Utility method to get active tab
    async getActiveTab() {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        return tab;
    }

    // Connection status management methods
    getConnectionStatus(tabId) {
        if (!tabId) {
            return {
                connected: false,
                sessionId: null,
                url: null,
                lastUpdate: null,
                error: 'No tab ID available'
            };
        }
        return this.connectionStates.get(tabId) || {
            connected: false,
            sessionId: null,
            url: null,
            lastUpdate: null
        };
    }

    async setConnectionStatus(tabId, connected) {
        try {
            if (!tabId) {
                throw new Error('No tab ID available');
            }
            const message = {
                type: connected ? 'CONNECT' : 'DISCONNECT'
            };
            await this.sendMessageToTab(tabId, message);
        } catch (error) {
            console.error('Error setting connection status:', error);
            throw error;
        }
    }

    updateConnectionStatus(tabId, status) {
        this.connectionStates.set(tabId, {
            ...status,
            lastUpdate: Date.now()
        });
    }

    async notifyPopupStatusChange(tabId, status) {
        // Try to send message to popup if it's open
        try {
            chrome.runtime.sendMessage({
                type: 'UPDATE_POPUP_STATUS',
                tabId: tabId,
                status: status
            });
        } catch (error) {
            // Popup might not be open, that's okay
            console.log('Popup not available for status update');
        }
    }

    // WebSocket连接到后端，用于接收浏览器操作命令
    connectToBackend() {
        try {
            // 连接到专门的浏览器操作WebSocket端点
            this.websocket = new WebSocket('ws://127.0.0.1:8000/ws/browser_control/');

            this.websocket.onopen = () => {
                console.log('Connected to FinGPT backend for browser control');
                this.reconnectAttempts = 0;
            };

            this.websocket.onmessage = (event) => {
                this.handleBackendMessage(JSON.parse(event.data));
            };

            this.websocket.onclose = () => {
                console.log('Disconnected from FinGPT backend');
                this.attemptReconnect();
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

        } catch (error) {
            console.error('Failed to connect to backend:', error);
            this.attemptReconnect();
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
            setTimeout(() => this.connectToBackend(), 5000);
        }
    }

    async handleBackendMessage(data) {
        console.log('Received backend message:', data);

        switch (data.type) {
            case 'browser_navigate':
                await this.executeBrowserNavigate(data.url);
                break;
            case 'browser_press_key':
                await this.executeBrowserPressKey(data.key);
                break;
            case 'browser_type':
                await this.executeBrowserType(data.text);
                break;
            case 'browser_click':
                await this.executeBrowserClick(data.selector);
                break;
            case 'browser_info':
                await this.executeBrowserInfo(data.request_id);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }

    async executeBrowserNavigate(url) {
        try {
            // 在当前活动标签页中导航到URL
            const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (activeTab) {
                await chrome.tabs.update(activeTab.id, { url: url });
                console.log(`Navigated to: ${url}`);

                // 发送确认消息回后端
                this.sendBackendResponse({
                    type: 'browser_navigate_result',
                    success: true,
                    url: url,
                    message: `Successfully navigated to ${url}`
                });
            }
        } catch (error) {
            console.error('Failed to navigate:', error);
            this.sendBackendResponse({
                type: 'browser_navigate_result',
                success: false,
                error: error.message
            });
        }
    }



    async executeBrowserPressKey(key) {
        try {
            // 向当前活动标签页的content script发送按键命令
            const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (activeTab) {
                await chrome.tabs.sendMessage(activeTab.id, {
                    type: 'press_key',
                    key: key
                });
                console.log(`Pressed key: ${key}`);

                this.sendBackendResponse({
                    type: 'browser_press_key_result',
                    success: true,
                    key: key,
                    message: `Successfully pressed key: ${key}`
                });
            }
        } catch (error) {
            console.error('Failed to press key:', error);
            this.sendBackendResponse({
                type: 'browser_press_key_result',
                success: false,
                error: error.message
            });
        }
    }

    async executeBrowserType(text) {
        try {
            // 向当前活动标签页的content script发送输入命令
            const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (activeTab) {
                await chrome.tabs.sendMessage(activeTab.id, {
                    type: 'type_text',
                    text: text
                });
                console.log(`Typed text: ${text}`);

                this.sendBackendResponse({
                    type: 'browser_type_result',
                    success: true,
                    text: text,
                    message: `Successfully typed: ${text}`
                });
            }
        } catch (error) {
            console.error('Failed to type text:', error);
            this.sendBackendResponse({
                type: 'browser_type_result',
                success: false,
                error: error.message
            });
        }
    }

    async executeBrowserClick(selector) {
        try {
            // 向当前活动标签页的content script发送点击命令
            const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (activeTab) {
                await chrome.tabs.sendMessage(activeTab.id, {
                    type: 'click_element',
                    selector: selector
                });
                console.log(`Clicked element: ${selector}`);

                this.sendBackendResponse({
                    type: 'browser_click_result',
                    success: true,
                    selector: selector,
                    message: `Successfully clicked element: ${selector}`
                });
            }
        } catch (error) {
            console.error('Failed to click element:', error);
            this.sendBackendResponse({
                type: 'browser_click_result',
                success: false,
                error: error.message
            });
        }
    }

    async executeBrowserInfo(requestId = 'default') {
        try {
            // 向当前活动标签页的content script请求页面信息
            const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (activeTab) {
                const response = await chrome.tabs.sendMessage(activeTab.id, {
                    type: 'get_page_info'
                });

                console.log('Got page info:', response);

                this.sendBackendResponse({
                    type: 'browser_info_result',
                    success: true,
                    pageInfo: response,
                    request_id: requestId,
                    message: 'Successfully retrieved page information'
                });
            }
        } catch (error) {
            console.error('Failed to get page info:', error);
            this.sendBackendResponse({
                type: 'browser_info_result',
                success: false,
                error: error.message,
                request_id: requestId
            });
        }
    }

    sendBackendResponse(data) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(data));
        }
    }
}

// Initialize background service
new FinGPTBackground();
