// content.js - Enhanced Content Script for FinGPT
import { postWebTextToServer, setSessionId } from './modules/api.js';
import { createUI } from './modules/ui.js';
import { fetchAvailableModels } from './modules/config.js';

// Prevent multiple injections
if (window.fingptInjected) {
    console.log('FinGPT already injected on this page');
} else {
    window.fingptInjected = true;

    // Generate a unique session ID for this page load
    const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setSessionId(sessionId);
    console.log("FinGPT Session ID: ", sessionId);

    const currentUrl = window.location.href.toString();
    console.log("Current page: ", currentUrl);

    const textContent = document.body.innerText || "";

    // Fetch available models from backend on startup
    fetchAvailableModels().then(() => {
        console.log("Models fetched from backend");
    }).catch(error => {
        console.error("CRITICAL: Failed to fetch models from backend:", error);
        alert(`Failed to connect to FinGPT backend: ${error.message}\n\nPlease ensure the backend server is running on http://localhost:8000`);
    });

    // POST JSON to the server endpoint
    postWebTextToServer(textContent, currentUrl)
        .then(data => {
            console.log("Response from server:", data);
        })
        .catch(error => {
            console.error("There was a problem with your fetch operation:", error);
        });

    // Initialize UI
    const { popup, settings_window, sources_window, searchQuery } = createUI();

    // Store UI references globally for extension icon control
    window.fingptUI = {
        popup,
        settings_window,
        sources_window,
        searchQuery,
        isVisible: true // UI starts visible by default
    };

    // Setup message listener for communication with background script
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.action === 'toggleUI') {
            toggleFinGPTUI();
            sendResponse({ success: true, visible: window.fingptUI.isVisible });
        } else if (message.action === 'getPageContent') {
            sendResponse({
                success: true,
                data: {
                    title: document.title,
                    url: window.location.href,
                    content: document.body.innerText || document.body.textContent || '',
                    timestamp: Date.now()
                }
            });
        }
        return true; // Keep message channel open
    });

    // Function to toggle FinGPT UI visibility
    function toggleFinGPTUI() {
        const ui = window.fingptUI;
        if (!ui) return;

        if (ui.isVisible) {
            // Hide UI
            if (ui.popup) ui.popup.style.display = 'none';
            if (ui.settings_window) ui.settings_window.style.display = 'none';
            if (ui.sources_window) ui.sources_window.style.display = 'none';
            ui.isVisible = false;
            console.log('FinGPT UI hidden');
        } else {
            // Show UI
            if (ui.popup) ui.popup.style.display = 'block';
            ui.isVisible = true;
            console.log('FinGPT UI shown');

            // Focus on search input if available
            if (ui.searchQuery) {
                setTimeout(() => ui.searchQuery.focus(), 100);
            }
        }
    }

    // Keyboard shortcut to toggle UI (Ctrl+Shift+F)
    document.addEventListener('keydown', (event) => {
        if (event.ctrlKey && event.shiftKey && event.key === 'F') {
            event.preventDefault();
            toggleFinGPTUI();
        }
    });

    console.log('FinGPT Enhanced content script initialized');
}


