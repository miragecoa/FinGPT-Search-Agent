// config.js

// Available models
const availableModels = ["o1-preview", "gpt-4o", "deepseek-reasoner"];

// Initialize a single selected model
let selectedModel = "o1-preview";

function getSelectedModel() {
    return selectedModel;
}

export { availableModels, selectedModel, getSelectedModel };