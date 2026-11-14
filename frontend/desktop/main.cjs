const { app, BrowserWindow } = require('electron');
const http = require('node:http');
const net = require('node:net');
const fs = require('node:fs');
const path = require('node:path');
let server;
const backend = new URL(process.env.BACKEND_URL || 'http://127.0.0.1:8000');
const types = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.glb':'model/gltf-binary', '.png':'image/png', '.jpg':'image/jpeg' };
async function start() {
  server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/static/')) {
      const upstream = http.request(new URL(req.url, backend), { method:req.method, headers:{ ...req.headers, host:backend.host } }, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
      upstream.on('error', () => { res.writeHead(503); res.end('Backend indisponibil'); });
      req.pipe(upstream); return;
    }
    const root = path.resolve(__dirname, '../dist');
    const file = path.resolve(root, '.' + decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
    if (!file.startsWith(root + path.sep)) { res.writeHead(403); res.end(); return; }
    fs.stat(file, (error, stat) => { if (error || !stat.isFile()) { res.writeHead(404); res.end(); return; } res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream'); fs.createReadStream(file).pipe(res); });
  });
  server.on('upgrade', (req, socket, head) => {
    if (req.url !== '/api/live') return socket.destroy();
    const upstream = net.connect(Number(backend.port || 80), backend.hostname, () => { upstream.write(`${req.method} ${req.url} HTTP/1.1\r\n` + Object.entries({ ...req.headers, host:backend.host }).map(([k,v]) => `${k}: ${v}`).join('\r\n') + '\r\n\r\n'); if(head.length) upstream.write(head); socket.pipe(upstream).pipe(socket); });
    upstream.on('error',()=>socket.destroy()); socket.on('error',()=>upstream.destroy()); socket.on('close',()=>upstream.destroy());
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const window = new BrowserWindow({ width:1440, height:950, minWidth:720, minHeight:600, title:'Marswalk Copilot', icon:path.join(__dirname,'../dist/images/marswalk-app-icon.png'), backgroundColor:'#090909', autoHideMenuBar:true, webPreferences:{ nodeIntegration:false, contextIsolation:true, sandbox:true } });
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',(event,url)=>{ if(new URL(url).origin !== origin) event.preventDefault(); });
  await window.loadURL(origin);
}
app.whenReady().then(start);
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',()=>server?.close());
