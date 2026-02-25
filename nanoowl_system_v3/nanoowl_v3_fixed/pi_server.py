#!/usr/bin/env python3
"""
NANOOWL VISION SYSTEM v3.0 - Pi Server (Raspberry Pi 3)
Ultra-lightweight MJPEG forwarding server
Does ZERO image processing - just forwards bytes from Jetson to clients
"""

import socket
import subprocess
import time
import threading
import json
import logging
import urllib.parse
from typing import Any

# Configuration constants
PI_IP = "0.0.0.0"
WEB_PORT = 8080
JETSON_IP = "127.0.0.1"  # localhost - change to actual Jetson IP if running on different machine
JETSON_USER = "jetson"
JETSON_PASSWORD = "jetson"
JETSON_CMD_PORT = 9003
CAMERA_PORTS = [9000, 9001]

# Logger setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class MJPEGForwarder:
    """MJPEG forwarder class"""
    def __init__(self, camera_id: int, port: int) -> None:
        self.camera_id = camera_id
        self.port = port
        self.connected = False
        self.clients: list[Any] = []
        self.running = True
        self.jetson_socket: Any = None
        self.lock = threading.Lock()
    
    def forward_frames(self) -> None:
        """Forward frames from Jetson to clients"""
        logger.info(f"Starting forwarder for camera {self.camera_id} on port {self.port}")
        
        while self.running:
            try:
                # Connect to Jetson
                logger.info(f"Connecting to Jetson {JETSON_IP}:{self.port}...")
                self.jetson_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.jetson_socket.settimeout(5)
                self.jetson_socket.connect((JETSON_IP, self.port))
                self.connected = True
                logger.info(f"Connected to camera {self.camera_id}")
                
                buffer = b""
                while self.running:
                    # Receive data from Jetson
                    data = self.jetson_socket.recv(4096)
                    if not data:
                        logger.warning(f"Camera {self.camera_id}: Connection closed by Jetson")
                        break
                    
                    buffer += data
                    
                    # Forward complete frames to all clients
                    while b"--frame\r\n" in buffer:
                        # Find frame boundaries
                        start = buffer.find(b"--frame\r\n")
                        next_frame = buffer.find(b"--frame\r\n", start + 9)
                        
                        if next_frame == -1:
                            break
                            
                        frame_data = buffer[start:next_frame]
                        buffer = buffer[next_frame:]
                        
                        # Send to all connected clients
                        with self.lock:
                            dead_clients: list[Any] = []
                            for client in self.clients:
                                try:
                                    if hasattr(client, "sendall"):
                                        client.sendall(frame_data)
                                    else:
                                        client.write(frame_data)
                                        if hasattr(client, "flush"):
                                            client.flush()
                                except Exception:
                                    dead_clients.append(client)
                            
                            # Remove disconnected clients
                            for client in dead_clients:
                                self.clients.remove(client)
                                
            except Exception as e:
                logger.error(f"Camera {self.camera_id} error: {e}")
                self.connected = False
                
            finally:
                if self.jetson_socket:
                    try:
                        self.jetson_socket.close()
                    except Exception:
                        pass
                    self.jetson_socket = None
                self.connected = False
                
            # Retry connection
            if self.running:
                logger.info(f"Camera {self.camera_id}: Retrying in 5 seconds...")
                time.sleep(5)
    
    def add_client(self, client: Any) -> None:
        """Add a client to receive frames"""
        with self.lock:
            self.clients.append(client)
            logger.info(f"Camera {self.camera_id}: Client added ({len(self.clients)} total)")
    
    def stop(self) -> None:
        """Stop the forwarder"""
        self.running = False
        if self.jetson_socket:
            try:
                self.jetson_socket.close()
            except Exception:
                pass


class PiServer:
    """Main server that handles web requests and camera forwarding"""
    
    def __init__(self) -> None:
        self.forwarders: list[MJPEGForwarder] = []
        self.web_server: Any = None
        self.running: bool = True

        
    def check_jetson_workers(self) -> tuple[bool, int | None]:
        """Check if Jetson workers are running"""
        try:
            # Try to connect to each port
            for port in CAMERA_PORTS:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex((JETSON_IP, port))
                    sock.close()
                    if result != 0:
                        return False, port
                except Exception:
                    return False, port
            return True, None
        except Exception as e:
            logger.error(f"Error checking Jetson workers: {e}")
            return False, None
            
    def start_jetson_workers(self) -> bool:
        """Start Jetson workers via SSH"""
        logger.info("Attempting to start Jetson workers via SSH...")
        try:
            # Use sshpass for password authentication
            cmd = [
                "sshpass", "-p", JETSON_PASSWORD,
                "ssh", "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                f"{JETSON_USER}@{JETSON_IP}",
                "cd ~/nanoowl_system_v3.0 && ./launch.sh"
            ]
            
            # Start in background
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("Jetson workers launch command sent")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Jetson workers: {e}")
            return False
            
    def start(self):
        """Start all services"""
        logger.info("=" * 60)
        logger.info("NanoOWL Pi Server v3.0 Starting...")
        logger.info("Ultra-lightweight MJPEG forwarding")
        logger.info("=" * 60)
        
        # Check if Jetson workers are running
        logger.info("Checking if Jetson workers are running...")
        workers_running, missing_port = self.check_jetson_workers()
        
        if not workers_running:
            logger.warning(f"Jetson worker not responding on port {missing_port}")
            logger.info("Attempting to auto-start Jetson workers...")
            
            if self.start_jetson_workers():
                logger.info("Waiting 10 seconds for Jetson workers to start...")
                time.sleep(10)
                
                # Check again
                workers_running, missing_port = self.check_jetson_workers()
                if not workers_running:
                    logger.error("=" * 60)
                    logger.error("Jetson workers failed to start!")
                    logger.error("Please manually start workers on Jetson:")
                    logger.error(f"  ssh {JETSON_USER}@{JETSON_IP}")
                    logger.error("  cd ~/nanoowl_system_v3.0")
                    logger.error("  ./launch.sh")
                    logger.error("=" * 60)
            else:
                logger.error("Failed to auto-start Jetson workers")
        else:
            logger.info("Jetson workers are running!")
        
        # Start camera forwarders
        logger.info("Starting camera forwarders...")
        for i, port in enumerate(CAMERA_PORTS):
            forwarder = MJPEGForwarder(i, port)
            self.forwarders.append(forwarder)
            threading.Thread(target=forwarder.forward_frames, daemon=True).start()
            
        # Start web server
        self.start_web_server()

    def send_prompt_to_jetson(self, text: str) -> bool:
        """Send a prompt update command to the Jetson worker."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((JETSON_IP, JETSON_CMD_PORT))
            payload = json.dumps({"cmd": "set_prompt", "text": text})
            sock.sendall(payload.encode())
            resp = sock.recv(1024)
            sock.close()
            return resp.strip().upper().startswith(b'OK')
        except Exception as e:
            logger.error(f"Failed to send prompt to Jetson: {e}")
            return False
        
    def start_web_server(self):
        """Start the HTTP web server"""
        import http.server
        import socketserver
        
        class Handler(http.server.BaseHTTPRequestHandler):
            pi_server = self
            
            def log_message(self, format: str, *args: Any) -> None:
                logger.info(format % args if args else format)
                
            def do_GET(self):
                if self.path == "/":
                    self.serve_main_page()
                elif self.path.startswith("/camera/"):
                    self.serve_camera_stream()
                elif self.path == "/status":
                    self.serve_status()
                elif self.path == "/start_jetson":
                    self.start_jetson()
                elif self.path.startswith("/set_prompt"):
                    # receive new prompt from query string
                    q = urllib.parse.urlparse(self.path).query
                    params = urllib.parse.parse_qs(q)
                    text = params.get('text', [''])[0]
                    if not text:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b"No prompt provided")
                    else:
                        ok = self.pi_server.send_prompt_to_jetson(text)
                        if ok:
                            self.send_response(200)
                            self.end_headers()
                            self.wfile.write(b"Prompt updated")
                        else:
                            self.send_response(500)
                            self.end_headers()
                            self.wfile.write(b"Failed to update prompt")
                else:
                    self.send_error(404)
                    
            def serve_main_page(self):
                """Serve the main web UI"""
                
                # Check camera statuses
                cam_status: list[str] = []
                for i, f in enumerate(self.pi_server.forwarders):
                    status: str = "connected" if f.connected else "disconnected"
                    cam_status.append(f"Camera {i}: {status}")
                
                html = f"""<!DOCTYPE html>
<html>
<head>
    <title>NanoOWL Vision v3.0</title>
    <style>
        body {{
            background: #1a1a2e;
            color: #eaeaea;
            font-family: 'Segoe UI', sans-serif;
            margin: 0;
            padding: 20px;
        }}
        h1 {{
            color: #00ff88;
            text-align: center;
            margin-bottom: 20px;
        }}
        .status-box {{
            background: #0d1117;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            text-align: center;
        }}
        .status-box h3 {{
            color: #4a9eff;
            margin: 0 0 10px 0;
        }}
        .status-connected {{ color: #00ff88; }}
        .status-disconnected {{ color: #ff6b6b; }}
        .cameras {{
            display: flex;
            justify-content: center;
            gap: 20px;
            flex-wrap: wrap;
        }}
        .camera-box {{
            background: #0d1117;
            border-radius: 10px;
            padding: 10px;
            text-align: center;
        }}
        .camera-box h3 {{
            color: #4a9eff;
            margin: 0 0 10px 0;
        }}
        .camera-box img {{
            border-radius: 5px;
            max-width: 640px;
            max-height: 480px;
        }}
        .controls {{
            text-align: center;
            margin: 20px 0;
        }}
        button {{
            background: #27ae60;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin: 0 5px;
            font-size: 14px;
        }}
        button:hover {{
            background: #2ecc71;
        }}
        button:disabled {{
            background: #555;
            cursor: not-allowed;
        }}
        .error {{
            background: #c0392b;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <h1>NanoOWL Vision System v3.0</h1>
    
    <div class="status-box">
        <h3>System Status</h3>
        <p>Pi Server: <span class="status-connected">Running</span></p>
        <p>Jetson: {JETSON_IP}</p>
        <p>{'<br>'.join(cam_status)}</p>
    </div>
    
    <div class="controls">
        <button onclick="location.reload()">Refresh</button>
        <button onclick="togglePause()">Pause/Resume</button>
        <button onclick="startJetson()">Start Jetson Workers</button>
    </div>
    <div class="controls">
        <input type="text" id="prompt" placeholder="Enter detection prompt" style="width:300px;">
        <button onclick="updatePrompt()">Set Prompt</button>
    </div>
    <div class="cameras">
        <div class="camera-box">
            <h3>Camera 0 - Detection Feed</h3>
            <img src="/camera/0" id="cam0" alt="Camera 0" onerror="this.style.display='none'; document.getElementById('err0').style.display='block';">
            <div id="err0" style="display:none; color:#ff6b6b;">Camera 0 not available<br>Check Jetson workers</div>
        </div>
        <div class="camera-box">
            <h3>Camera 1 - Raw Feed</h3>
            <img src="/camera/1" id="cam1" alt="Camera 1" onerror="this.style.display='none'; document.getElementById('err1').style.display='block';">
            <div id="err1" style="display:none; color:#ff6b6b;">Camera 1 not available<br>Check Jetson workers</div>
        </div>
    </div>
    
    <script>
        let paused = false;
        function togglePause() {{
            paused = !paused;
            document.getElementById('cam0').style.display = paused ? 'none' : 'block';
            document.getElementById('cam1').style.display = paused ? 'none' : 'block';
        }}
        
        function startJetson() {{
            fetch('/start_jetson')
                .then(response => response.text())
                .then(data => alert(data))
                .catch(err => alert('Error: ' + err));
        }}

        function updatePrompt() {{
            const txt = document.getElementById('prompt').value;
            if (!txt) return alert('Please enter prompt text');
            fetch('/set_prompt?text=' + encodeURIComponent(txt))
                .then(r => r.text())
                .then(t => alert(t))
                .catch(e => alert('Error: '+e));
        }}
    </script>
</body>
</html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(html.encode())
                
            def serve_camera_stream(self):
                """Serve MJPEG camera stream"""
                try:
                    camera_id = int(self.path.split("/")[2])
                    if camera_id >= len(self.pi_server.forwarders):
                        self.send_error(404)
                        return
                        
                    forwarder = self.pi_server.forwarders[camera_id]
                    
                    # Wait up to 10 seconds for connection
                    wait_time = 0
                    while not forwarder.connected and wait_time < 10:
                        time.sleep(0.5)
                        wait_time += 0.5
                    
                    if not forwarder.connected:
                        self.send_error(503, "Camera not connected after 10s")
                        return
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    
                    # Add this client's wfile to forwarder
                    forwarder.add_client(self.wfile)
                    
                    # Keep connection alive - the forwarder will write to wfile
                    while self.pi_server.running and forwarder.connected:
                        time.sleep(0.1)
                        
                except Exception as e:
                    logger.error(f"Camera stream error: {e}")
                    
            def serve_status(self) -> None:
                """Serve system status"""
                import json
                status: dict[str, Any] = {
                    "pi_server": "running",
                    "jetson_ip": JETSON_IP,
                    "cameras": [
                        {
                            "id": i,
                            "clients": len(f.clients),
                            "connected": f.connected
                        }
                        for i, f in enumerate(self.pi_server.forwarders)
                    ]
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(status).encode())
                
            def start_jetson(self):
                """Start Jetson workers via API"""
                if self.pi_server.start_jetson_workers():
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Jetson workers start command sent. Wait 10 seconds and refresh.")
                else:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"Failed to start Jetson workers. Check logs.")
                
        # Create a TCPServer subclass so we can enable address reuse
        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        try:
            httpd = ReusableTCPServer((PI_IP, WEB_PORT), Handler)
        except OSError as err:
            logger.error(f"Failed to bind web server to {PI_IP}:{WEB_PORT}: {err}")
            logger.error("Is another process already listening on that port?\n")
            # raise to let caller decide; server.start() will abort
            raise

        # keep reference so stop() can shut it down
        self.web_server = httpd

        logger.info(f"Web server started on http://{PI_IP}:{WEB_PORT}")
        logger.info(f"Web UI: http://192.168.50.1:{WEB_PORT}")

        # run in foreground; serve_forever blocks until shutdown()
        try:
            httpd.serve_forever()
        except Exception as e:
            logger.error(f"Web server error: {e}")
        finally:
            try:
                httpd.server_close()
            except Exception:
                pass
                
    def stop(self):
        """Stop all services"""
        self.running = False
        for forwarder in self.forwarders:
            forwarder.stop()
        # shut down web server if running
        if hasattr(self, "web_server") and self.web_server:
            try:
                self.web_server.shutdown()
                self.web_server.server_close()
            except Exception as e:
                logger.debug(f"Error during web server shutdown: {e}")


if __name__ == "__main__":
    server = PiServer()
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.stop()
