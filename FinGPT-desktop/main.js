const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require('electron');
const path = require('path');

let mainWindow;
let windowState = {
    width: 400,
    height: 600,
    x: undefined,
    y: undefined,
    isVisible: true  // 默认显示窗口
};

function createWindow() {
    // 获取主显示器信息
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
    
    // 如果没有保存的位置，默认在右侧
    if (windowState.x === undefined || windowState.y === undefined) {
        windowState.x = screenWidth - windowState.width - 20;
        windowState.y = 100;
    }
    
    mainWindow = new BrowserWindow({
        width: windowState.width,
        height: windowState.height,
        x: windowState.x,
        y: windowState.y,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            enableRemoteModule: true
        },
        frame: true,
        resizable: true,
        alwaysOnTop: true,
        skipTaskbar: false,
        show: windowState.isVisible,
        title: 'FinGPT Assistant'
    });

    // 加载HTML文件
    mainWindow.loadFile('renderer.html');

    // 窗口事件处理
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
    
    mainWindow.on('resize', () => {
        const bounds = mainWindow.getBounds();
        windowState.width = bounds.width;
        windowState.height = bounds.height;
    });
    
    mainWindow.on('move', () => {
        const bounds = mainWindow.getBounds();
        windowState.x = bounds.x;
        windowState.y = bounds.y;
    });
    
    mainWindow.on('show', () => {
        windowState.isVisible = true;
    });
    
    mainWindow.on('hide', () => {
        windowState.isVisible = false;
    });

    // 开发工具
    if (process.env.NODE_ENV === 'development') {
        mainWindow.webContents.openDevTools();
    }
}

function toggleWindow() {
    if (mainWindow) {
        if (mainWindow.isVisible()) {
            mainWindow.hide();
        } else {
            mainWindow.show();
            mainWindow.focus();
        }
    } else {
        createWindow();
    }
}

app.whenReady().then(() => {
    createWindow();
    
    // 注册全局快捷键 Ctrl+Shift+F
    globalShortcut.register('CommandOrControl+Shift+F', () => {
        toggleWindow();
    });
    
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('will-quit', () => {
    // 注销所有快捷键
    globalShortcut.unregisterAll();
});

// IPC 事件处理
ipcMain.handle('toggle-window', () => {
    toggleWindow();
});

ipcMain.handle('get-window-state', () => {
    return windowState;
});

ipcMain.handle('set-window-state', (event, newState) => {
    windowState = { ...windowState, ...newState };
    if (mainWindow) {
        if (newState.width || newState.height) {
            mainWindow.setSize(newState.width || windowState.width, newState.height || windowState.height);
        }
        if (newState.x !== undefined || newState.y !== undefined) {
            mainWindow.setPosition(newState.x !== undefined ? newState.x : windowState.x, 
                                 newState.y !== undefined ? newState.y : windowState.y);
        }
    }
});
