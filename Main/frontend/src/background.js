// background.js - Service Worker for FinGPT Enhanced

class FinGPTBackground {
    constructor() {
        this.init();
    }

    init() {
        this.setupEventListeners();
        console.log('FinGPT Enhanced background service worker initialized');
    }

    setupEventListeners() {
        // Handle extension installation
        chrome.runtime.onInstalled.addListener((details) => {
            this.handleInstallation(details);
        });

        // Handle messages from content scripts and popup
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            this.handleMessage(message, sender, sendResponse);
            return true; // Keep message channel open for async responses
        });

        // Handle tab updates to inject content script if needed
        chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
            this.handleTabUpdate(tabId, changeInfo, tab);
        });

        // Handle browser action click
        chrome.action.onClicked.addListener((tab) => {
            this.handleActionClick(tab);
        });
    }

    handleInstallation(details) {
        console.log('FinGPT Enhanced installed:', details.reason);
        
        if (details.reason === 'install') {
            // Set default settings on first install
            chrome.storage.local.set({
                fingptSettings: {
                    apiEndpoint: 'http://127.0.0.1:8000',
                    defaultModel: 'gpt-4',
                    autoGetContent: false,
                    enableMcp: true
                }
            });

            // Open welcome page or show notification
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
        try {
            // Send message to content script to toggle UI
            const response = await chrome.tabs.sendMessage(tab.id, { action: 'toggleUI' });
            console.log('UI toggled:', response);
        } catch (error) {
            console.error('Error toggling UI:', error);

            // If content script is not injected, inject it first
            try {
                await this.injectContentScript(tab.id);
                // Try again after injection
                setTimeout(async () => {
                    try {
                        await chrome.tabs.sendMessage(tab.id, { action: 'toggleUI' });
                    } catch (e) {
                        console.error('Failed to toggle UI after injection:', e);
                    }
                }, 500);
            } catch (injectionError) {
                console.error('Failed to inject content script:', injectionError);
            }
        }
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
}

// Initialize background service
new FinGPTBackground();
