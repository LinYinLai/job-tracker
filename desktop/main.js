const { app, BrowserWindow, ipcMain, shell, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const PORT = 8001;
const URL = `http://127.0.0.1:${PORT}`;

let flask = null;
let mainWin = null;

function startFlask() {
  const backendDir = path.join(__dirname, '..', 'backend');
  // macOS 默认只有 python3，Windows 是 python；也可用环境变量 JOBTRACKER_PYTHON 指定具体解释器
  const PY = process.env.JOBTRACKER_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  flask = spawn(PY, ['app.py'], { cwd: backendDir, windowsHide: true });
  flask.stdout.on('data', d => process.stdout.write('[flask] ' + d));
  flask.stderr.on('data', d => process.stderr.write('[flask] ' + d));
}

function waitForServer(cb, tries = 60) {
  const req = http.get(URL + '/api/widget', res => { res.resume(); cb(); });
  req.on('error', () => {
    if (tries > 0) setTimeout(() => waitForServer(cb, tries - 1), 500);
    else console.error('Flask 启动超时');
  });
  req.setTimeout(3000, () => req.destroy());
}

function createMainWindow() {
  mainWin = new BrowserWindow({
    width: 480, height: 840,
    frame: false, transparent: true, backgroundColor: '#00000000', hasShadow: false,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false }
  });
  // 外部链接（投递网址等）用系统默认浏览器打开，不在 App 内开新窗
  mainWin.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  // 右键菜单：复制/剪切/粘贴/全选（Electron 默认不提供）
  mainWin.webContents.on('context-menu', (e, params) => {
    const menu = Menu.buildFromTemplate([
      { role: 'cut', label: '剪切', enabled: params.editFlags.canCut },
      { role: 'copy', label: '复制', enabled: params.editFlags.canCopy },
      { role: 'paste', label: '粘贴', enabled: params.editFlags.canPaste },
      { type: 'separator' },
      { role: 'selectAll', label: '全选', enabled: params.editFlags.canSelectAll },
    ]);
    menu.popup();
  });
  mainWin.loadURL(URL + '/');
  mainWin.on('closed', () => { mainWin = null; app.quit(); });
}

app.whenReady().then(() => {
  startFlask();
  waitForServer(createMainWindow);
});

ipcMain.on('window-minimize', (e) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win) win.minimize();
});

ipcMain.on('window-close', (e) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win) win.close();
});

app.on('before-quit', () => {
  if (flask) { try { flask.kill(); } catch (e) {} }
});
