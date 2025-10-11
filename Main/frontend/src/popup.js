// popup.js - FinGPT Extension Popup
class FinGPTPopup {
    constructor() {
        this.currentTab = null;
        this.connectionStatus = null;
        this.init();
    }

    async init() {
        console.log('FinGPT Popup initialized');
        
        // Get current active tab
        await this.getCurrentTab();
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Load initial status
        await this.loadConnectionStatus();
        
        // Setup message listener for status updates
        this.setupMessageListener();
    }

    async getCurrentTab() {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            this.currentTab = tab;
            console.log('Current tab:', tab ? tab.url : 'No tab found');
        } catch (error) {
            console.error('Error getting current tab:', error);
            this.currentTab = null;
        }
    }

    setupEventListeners() {
        // Connect/Disconnect button
        const connectBtn = document.getElementById('connectBtn');
        if (connectBtn) {
            connectBtn.addEventListener('click', () => this.toggleConnection());
        }
    }

    setupMessageListener() {
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            if (message.type === 'UPDATE_POPUP_STATUS') {
                this.updateStatus(message.status);
            }
            return true;
        });
    }

    async loadConnectionStatus() {
        try {
            // Request connection status from background script
            const response = await chrome.runtime.sendMessage({
                type: 'GET_CONNECTION_STATUS'
            });

            if (response && response.success) {
                this.connectionStatus = response.data;
                this.updateUI(this.connectionStatus);
            } else {
                throw new Error(response ? response.error : 'No response from background script');
            }
        } catch (error) {
            console.error('Error loading connection status:', error);
            this.updateUI({
                connected: false,
                error: error.message || 'Connection status unavailable'
            });
        }
    }

    async toggleConnection() {
        try {
            if (!this.currentTab || !this.currentTab.id) {
                throw new Error('No active tab available');
            }

            const connectBtn = document.getElementById('connectBtn');
            connectBtn.disabled = true;

            const newStatus = !this.connectionStatus?.connected;
            
            // Update UI to show connecting/disconnecting state
            this.updateUI({
                connected: newStatus,
                connecting: true
            });

            // Send connection command to background script
            const response = await chrome.runtime.sendMessage({
                type: 'SET_CONNECTION_STATUS',
                connected: newStatus
            });

            if (!response.success) {
                throw new Error(response.error);
            }

            // Reload status after a short delay
            setTimeout(() => {
                this.loadConnectionStatus();
            }, 1000);

        } catch (error) {
            console.error('Error toggling connection:', error);
            this.updateUI({
                connected: false,
                error: error.message
            });
        }
    }

    updateStatus(status) {
        this.connectionStatus = status;
        this.updateUI(status);
    }

    updateUI(status) {
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        const connectBtn = document.getElementById('connectBtn');
        const btnText = document.getElementById('btnText');
        const sessionInfo = document.getElementById('sessionInfo');
        const sessionId = document.getElementById('sessionId');
        const pageInfo = document.getElementById('pageInfo');
        const currentPage = document.getElementById('currentPage');

        // Remove all status classes
        statusDot.classList.remove('connected', 'disconnected', 'connecting');
        connectBtn.classList.remove('connect', 'disconnect');

        if (status.connecting) {
            // Connecting/Disconnecting state
            statusDot.classList.add('connecting');
            statusText.textContent = status.connected ? 'Connecting...' : 'Disconnecting...';
            btnText.textContent = status.connected ? 'Connecting...' : 'Disconnecting...';
            connectBtn.disabled = true;
        } else if (status.connected) {
            // Connected state
            statusDot.classList.add('connected');
            statusText.textContent = 'Connected to FinGPT Server';
            btnText.textContent = 'Disconnect';
            connectBtn.classList.add('disconnect');
            connectBtn.disabled = false;

            // Show session info
            if (status.sessionId) {
                sessionId.textContent = status.sessionId.substring(0, 20) + '...';
                sessionInfo.style.display = 'block';
            }

            // Show page info
            if (status.url) {
                const url = new URL(status.url);
                currentPage.textContent = url.hostname + url.pathname;
                pageInfo.style.display = 'block';
            }
        } else {
            // Disconnected state
            statusDot.classList.add('disconnected');
            statusText.textContent = status.error || 'Not connected';
            btnText.textContent = 'Connect';
            connectBtn.classList.add('connect');
            connectBtn.disabled = false;

            // Hide additional info
            sessionInfo.style.display = 'none';
            pageInfo.style.display = 'none';
        }
    }


}

// Initialize popup when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new FinGPTPopup();
});
