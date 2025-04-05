// settings_window.js
import { availableModels, selectedModel } from '../config.js';
import { loadPreferredLinks, createAddLinkButton } from '../helpers.js';

function createSettingsWindow(isFixedModeRef, settingsIcon, positionModeIcon) {
    const settings_window = document.createElement('div');
    settings_window.style.display = "none";
    settings_window.id = "settings_window";

    const label = document.createElement('label');
    label.innerText = "Light Mode";
    const lightSwitch = document.createElement('input');
    lightSwitch.type = "checkbox";
    lightSwitch.onchange = () => document.body.classList.toggle('light-mode');
    label.appendChild(lightSwitch);
    settings_window.appendChild(label);

    const modelContainer = document.createElement('div');
    modelContainer.id = "model_selection_container";

    const modelHeader = document.createElement('div');
    modelHeader.id = "model_selection_header";
    modelHeader.innerText = `Model: ${selectedModel}`;

    const modelToggleIcon = document.createElement('span');
    modelToggleIcon.innerText = "⯆";

    modelHeader.appendChild(modelToggleIcon);
    modelContainer.appendChild(modelHeader);

    const modelContent = document.createElement('div');
    modelContent.id = "model_selection_content";
    modelContent.style.display = "none";

    function handleModelSelection(modelItem, modelName) {
        document.querySelectorAll('.model-selection-item').forEach(item => item.classList.remove('selected-model'));
        window.selectedModel = modelName;
        modelItem.classList.add('selected-model');
        modelHeader.innerText = `Model: ${modelName}`;
        modelHeader.appendChild(modelToggleIcon);
    }

    availableModels.forEach(model => {
        const item = document.createElement('div');
        item.className = 'model-selection-item';
        item.innerText = model;
        if (model === selectedModel) item.classList.add('selected-model');
        item.onclick = () => handleModelSelection(item, model);
        modelContent.appendChild(item);
    });

    modelContainer.appendChild(modelContent);
    settings_window.appendChild(modelContainer);

    modelHeader.onclick = () => {
        modelContent.style.display = modelContent.style.display === "none" ? "block" : "none";
        modelToggleIcon.innerText = modelContent.style.display === "none" ? "⯆" : "⯅";
    };

    const preferredLinksContainer = document.createElement('div');
    preferredLinksContainer.id = "preferred_links_container";

    const preferredLinksHeader = document.createElement('div');
    preferredLinksHeader.id = "preferred_links_header";
    preferredLinksHeader.innerText = "Preferred Links";

    const toggleIcon = document.createElement('span');
    toggleIcon.innerText = "⯆";
    preferredLinksHeader.appendChild(toggleIcon);
    preferredLinksContainer.appendChild(preferredLinksHeader);

    const preferredLinksContent = document.createElement('div');
    preferredLinksContent.id = "preferred_links_content";
    preferredLinksContent.appendChild(createAddLinkButton());

    preferredLinksContainer.appendChild(preferredLinksContent);
    settings_window.appendChild(preferredLinksContainer);

    preferredLinksHeader.onclick = function () {
        const isHidden = preferredLinksContent.style.display === "none";
        preferredLinksContent.style.display = isHidden ? "block" : "none";
        toggleIcon.innerText = isHidden ? "⯅" : "⯆";
    };

    const ragLabel = document.createElement('label');
    ragLabel.innerText = "Local RAG";
    const ragSwitch = document.createElement('input');
    ragSwitch.type = "checkbox";
    ragSwitch.id = "ragSwitch";
    ragLabel.appendChild(ragSwitch);
    settings_window.appendChild(ragLabel);

    settingsIcon.onclick = function (event) {
        event.stopPropagation();
        const rect = settingsIcon.getBoundingClientRect();
        const y = rect.bottom + (isFixedModeRef.value ? 0 : window.scrollY);
        const x = rect.left + (isFixedModeRef.value ? 0 : window.scrollX);
        settings_window.style.top = `${y}px`;
        settings_window.style.left = `${x}px`;
        settings_window.style.display = settings_window.style.display === 'none' ? 'block' : 'none';
        settings_window.style.position = isFixedModeRef.value ? 'fixed' : 'absolute';
        if (settings_window.style.display === 'block') loadPreferredLinks();
    };

    document.addEventListener('click', function (event) {
        if (
            settings_window.style.display === 'block' &&
            !settings_window.contains(event.target) &&
            !settingsIcon.contains(event.target) &&
            !positionModeIcon.contains(event.target)
        ) {
            settings_window.style.display = 'none';
        }
    });

    return settings_window;
}

export { createSettingsWindow };
