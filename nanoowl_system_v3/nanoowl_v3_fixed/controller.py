#!/usr/bin/env python3
"""
NANOOWL VISION SYSTEM v3.0 - Controller (Raspberry Pi 3)
GUI with dual logs, shutdown controls, WiFi IP display
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import socket
import os
import signal
import sys
import paramiko
import time
import requests

# Configuration
JETSON_IP = "192.168.50.2"
JETSON_USER = "jetson"
JETSON_PASSWORD = "jetson"  # <-- CHANGE THIS TO YOUR JETSON PASSWORD
PI_IP_ETH = "192.168.50.1"
WEB_PORT = 7860
CAMERA_PORTS = [9000, 9001, 9002]

# Colors
COLOR_BG = "#1a1a2e"
COLOR_FG = "#eaeaea"
COLOR_PI_LOG = "#00ff88"      # Green for Pi logs
COLOR_JETSON_LOG = "#4a9eff"  # Blue for Jetson logs
COLOR_ACCENT = "#ff6b6b"

class NanoOWLController:
    def __init__(self, root):
        self.root = root
        self.root.title("NanoOWL Vision System v3.0 - Controller")
        self.root.configure(bg=COLOR_BG)
        self.root.geometry("1200x800")
        
        # SSH connection to Jetson
        self.jetson_ssh = None
        self.jetson_shell = None
        
        # Processes
        self.pi_server_process = None
        self.web_server_process = None
        
        # Build UI
        self.build_ui()
        
        # Start background threads
        self.running = True
        self.start_ip_monitor()
        self.connect_to_jetson()
        
    def build_ui(self):
        # Main container
        main_frame = tk.Frame(self.root, bg=COLOR_BG)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header
        header = tk.Frame(main_frame, bg=COLOR_BG)
        header.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header, text="NanoOWL Vision System v3.0", 
                font=("Helvetica", 20, "bold"),
                bg=COLOR_BG, fg=COLOR_FG).pack(side=tk.LEFT)
        
        # Status frame
        status_frame = tk.Frame(header, bg=COLOR_BG)
        status_frame.pack(side=tk.RIGHT)
        
        self.wifi_ip_label = tk.Label(status_frame, text="WiFi IP: --", 
                                     font=("Helvetica", 10),
                                     bg=COLOR_BG, fg=COLOR_FG)
        self.wifi_ip_label.pack(side=tk.RIGHT, padx=10)
        
        self.eth_ip_label = tk.Label(status_frame, text=f"Eth: {PI_IP_ETH}", 
                                    font=("Helvetica", 10),
                                    bg=COLOR_BG, fg=COLOR_FG)
        self.eth_ip_label.pack(side=tk.RIGHT, padx=10)
        
        self.jetson_status_label = tk.Label(status_frame, text="Jetson: Disconnected", 
                                           font=("Helvetica", 10),
                                           bg=COLOR_BG, fg=COLOR_ACCENT)
        self.jetson_status_label.pack(side=tk.RIGHT, padx=10)
        
        # Control buttons frame
        control_frame = tk.Frame(main_frame, bg=COLOR_BG)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Button(control_frame, text="Start System", command=self.start_system,
                 bg="#27ae60", fg="white", font=("Helvetica", 12, "bold"),
                 width=12).pack(side=tk.LEFT, padx=5)
        
        tk.Button(control_frame, text="Stop System", command=self.stop_system,
                 bg="#e74c3c", fg="white", font=("Helvetica", 12, "bold"),
                 width=12).pack(side=tk.LEFT, padx=5)
        
        tk.Button(control_frame, text="Restart Jetson", command=self.restart_jetson,
                 bg="#f39c12", fg="white", font=("Helvetica", 12, "bold"),
                 width=12).pack(side=tk.LEFT, padx=5)
        
        # Shutdown buttons
        shutdown_frame = tk.LabelFrame(main_frame, text="Shutdown", 
                                      bg=COLOR_BG, fg=COLOR_FG,
                                      font=("Helvetica", 10))
        shutdown_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Button(shutdown_frame, text="Shutdown Pi Only", command=lambda: self.shutdown("pi"),
                 bg="#c0392b", fg="white", width=15).pack(side=tk.LEFT, padx=5, pady=5)
        
        tk.Button(shutdown_frame, text="Shutdown Jetson Only", command=lambda: self.shutdown("jetson"),
                 bg="#c0392b", fg="white", width=15).pack(side=tk.LEFT, padx=5, pady=5)
        
        tk.Button(shutdown_frame, text="Shutdown Both", command=lambda: self.shutdown("both"),
                 bg="#8e44ad", fg="white", width=15).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Logs frame
        logs_frame = tk.Frame(main_frame, bg=COLOR_BG)
        logs_frame.pack(fill=tk.BOTH, expand=True)
        
        # Pi Logs
        pi_frame = tk.LabelFrame(logs_frame, text="Pi Logs (Local)", 
                                bg=COLOR_BG, fg=COLOR_PI_LOG,
                                font=("Helvetica", 11, "bold"))
        pi_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.pi_log = scrolledtext.ScrolledText(pi_frame, wrap=tk.WORD,
                                                bg="#0d1117", fg=COLOR_PI_LOG,
                                                font=("Consolas", 9),
                                                state=tk.DISABLED)
        self.pi_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Jetson Logs
        jetson_frame = tk.LabelFrame(logs_frame, text="Jetson Logs (Remote)", 
                                    bg=COLOR_BG, fg=COLOR_JETSON_LOG,
                                    font=("Helvetica", 11, "bold"))
        jetson_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.jetson_log = scrolledtext.ScrolledText(jetson_frame, wrap=tk.WORD,
                                                   bg="#0d1117", fg=COLOR_JETSON_LOG,
                                                   font=("Consolas", 9),
                                                   state=tk.DISABLED)
        self.jetson_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Web UI link
        link_frame = tk.Frame(main_frame, bg=COLOR_BG)
        link_frame.pack(fill=tk.X, pady=(10, 0))
        
        tk.Label(link_frame, text="Web UI: ", bg=COLOR_BG, fg=COLOR_FG,
                font=("Helvetica", 10)).pack(side=tk.LEFT)
        
        self.web_link = tk.Label(link_frame, text=f"http://{PI_IP_ETH}:{WEB_PORT}",
                                bg=COLOR_BG, fg="#3498db",
                                font=("Helvetica", 10, "underline"),
                                cursor="hand2")
        self.web_link.pack(side=tk.LEFT)
        self.web_link.bind("<Button-1>", lambda e: self.open_web_ui())
        
        # Power monitoring
        power_frame = tk.LabelFrame(main_frame, text="Jetson Power Monitor", 
                                   bg=COLOR_BG, fg=COLOR_FG)
        power_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.power_label = tk.Label(power_frame, text="Power: --W | GPU: --% | Temp: --°C",
                                   bg=COLOR_BG, fg=COLOR_FG,
                                   font=("Consolas", 10))
        self.power_label.pack(padx=5, pady=5)
        
    def log_pi(self, message):
        """Log message to Pi log (green)"""
        self.pi_log.configure(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.pi_log.insert(tk.END, f"[{timestamp}] {message}\n")
        self.pi_log.see(tk.END)
        self.pi_log.configure(state=tk.DISABLED)
        
    def log_jetson(self, message):
        """Log message to Jetson log (blue)"""
        self.jetson_log.configure(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.jetson_log.insert(tk.END, f"[{timestamp}] {message}\n")
        self.jetson_log.see(tk.END)
        self.jetson_log.configure(state=tk.DISABLED)
        
    def get_wifi_ip(self):
        """Get WiFi IP address"""
        try:
            result = subprocess.run(
                ["hostname -I | awk '{print $1}'"],
                shell=True, capture_output=True, text=True
            )
            ips = result.stdout.strip().split()
            for ip in ips:
                if ip != PI_IP_ETH and not ip.startswith("127"):
                    return ip
        except Exception as e:
            self.log_pi(f"Error getting WiFi IP: {e}")
        return None
        
    def start_ip_monitor(self):
        """Monitor IP addresses in background"""
        def monitor():
            while self.running:
                wifi_ip = self.get_wifi_ip()
                if wifi_ip:
                    self.wifi_ip_label.config(text=f"WiFi IP: {wifi_ip}")
                time.sleep(5)
        threading.Thread(target=monitor, daemon=True).start()
        
    def connect_to_jetson(self):
        """Establish SSH connection to Jetson with password authentication"""
        def connect():
            try:
                self.log_pi("Connecting to Jetson via SSH...")
                self.jetson_ssh = paramiko.SSHClient()
                self.jetson_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Connect with password
                self.jetson_ssh.connect(
                    JETSON_IP, 
                    username=JETSON_USER, 
                    password=JETSON_PASSWORD,
                    timeout=10,
                    look_for_keys=False,  # Don't try SSH keys first
                    allow_agent=False     # Don't use SSH agent
                )
                
                self.jetson_shell = self.jetson_ssh.invoke_shell()
                self.jetson_status_label.config(text="Jetson: Connected", fg=COLOR_PI_LOG)
                self.log_pi("SSH connection to Jetson established")
                
                # Start reading Jetson output
                self.read_jetson_output()
                
            except paramiko.AuthenticationException:
                self.log_pi("SSH Authentication failed! Check JETSON_PASSWORD in controller.py")
                self.jetson_status_label.config(text="Jetson: Auth Failed", fg=COLOR_ACCENT)
            except Exception as e:
                self.log_pi(f"Failed to connect to Jetson: {e}")
                self.jetson_status_label.config(text="Jetson: Failed", fg=COLOR_ACCENT)
                
        threading.Thread(target=connect, daemon=True).start()
        
    def read_jetson_output(self):
        """Read output from Jetson SSH shell"""
        def read():
            while self.running and self.jetson_shell:
                try:
                    if self.jetson_shell.recv_ready():
                        data = self.jetson_shell.recv(4096).decode('utf-8', errors='ignore')
                        if data:
                            self.log_jetson(data.strip())
                    time.sleep(0.1)
                except Exception as e:
                    self.log_jetson(f"Error reading from Jetson: {e}")
                    break
                    
        threading.Thread(target=read, daemon=True).start()
        
    def send_jetson_command(self, command):
        """Send command to Jetson via SSH"""
        if self.jetson_shell:
            self.jetson_shell.send(command + "\n")
            self.log_pi(f"Sent to Jetson: {command}")
        else:
            self.log_pi("Jetson SSH not connected!")
            
    def start_system(self):
        """Start all system components"""
        self.log_pi("Starting NanoOWL Vision System v3.0...")
        
        # Start pi_server.py
        self.start_pi_server()
        
        # Start Jetson workers
        self.start_jetson_workers()
        
        # Start power monitoring
        self.start_power_monitor()
        
    def start_pi_server(self):
        """Start the lightweight Pi server"""
        def run():
            try:
                self.log_pi("Starting pi_server.py...")
                self.pi_server_process = subprocess.Popen(
                    ["python3", "pi_server.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )
                
                for line in self.pi_server_process.stdout:
                    self.log_pi(f"[pi_server] {line.strip()}")
                    
            except Exception as e:
                self.log_pi(f"Error starting pi_server: {e}")
                
        threading.Thread(target=run, daemon=True).start()
        
    def check_jetson_workers(self):
        """Check if Jetson workers are running on required ports"""
        import socket
        ports = [9000, 9001, 9002]
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((JETSON_IP, port))
                sock.close()
                if result != 0:
                    return False, port
            except Exception as e:
                return False, port
        return True, None
        
    def start_jetson_workers(self):
        """Start workers on Jetson"""
        self.log_pi("Checking Jetson workers...")
        
        # Check if workers are already running
        running, missing_port = self.check_jetson_workers()
        if running:
            self.log_pi("Jetson workers are already running!")
            return
            
        self.log_pi(f"Jetson worker not responding on port {missing_port}")
        self.log_pi("Starting Jetson workers via SSH...")
        
        if self.jetson_ssh:
            # Use exec_command for non-interactive commands
            try:
                stdin, stdout, stderr = self.jetson_ssh.exec_command(
                    "cd ~/nanoowl_system_v3.0 && nohup ./launch.sh > /dev/null 2>&1 &"
                )
                self.log_pi("Jetson workers launch command sent")
                self.log_pi("Waiting 10 seconds for workers to start...")
                
                # Wait and check again
                import time
                time.sleep(10)
                
                running, missing_port = self.check_jetson_workers()
                if running:
                    self.log_pi("Jetson workers are now running!")
                else:
                    self.log_pi(f"WARNING: Workers still not responding on port {missing_port}")
                    self.log_pi("Check Jetson logs manually")
                    
            except Exception as e:
                self.log_pi(f"Error starting Jetson workers: {e}")
        else:
            self.log_pi("Cannot start Jetson workers - SSH not connected")
        
    def start_power_monitor(self):
        """Monitor Jetson power and temperature"""
        def monitor():
            while self.running:
                try:
                    if self.jetson_ssh:
                        stdin, stdout, stderr = self.jetson_ssh.exec_command(
                            "tegrastats --interval 1000 | head -1"
                        )
                        stats = stdout.read().decode().strip()
                        if stats:
                            # Parse tegrastats output
                            self.power_label.config(text=f"Jetson: {stats}")
                except Exception as e:
                    pass
                time.sleep(2)
                
        threading.Thread(target=monitor, daemon=True).start()
        
    def stop_system(self):
        """Stop all system components"""
        self.log_pi("Stopping system...")
        
        # Stop Pi server
        if self.pi_server_process:
            self.pi_server_process.terminate()
            self.log_pi("Pi server stopped")
            
        # Stop Jetson workers
        self.send_jetson_command("pkill -f camera_worker.py")
        self.send_jetson_command("pkill -f detection_worker.py")
        self.log_pi("Jetson workers stopped")
        
    def restart_jetson(self):
        """Restart Jetson device"""
        if messagebox.askyesno("Confirm", "Restart Jetson?"):
            self.log_pi("Restarting Jetson...")
            self.send_jetson_command("sudo reboot")
            
    def shutdown(self, target):
        """Shutdown devices"""
        if target == "pi":
            if messagebox.askyesno("Confirm", "Shutdown Raspberry Pi?"):
                self.log_pi("Shutting down Pi...")
                os.system("sudo shutdown now")
        elif target == "jetson":
            if messagebox.askyesno("Confirm", "Shutdown Jetson?"):
                self.log_pi("Shutting down Jetson...")
                self.send_jetson_command("sudo shutdown now")
        elif target == "both":
            if messagebox.askyesno("Confirm", "Shutdown BOTH Pi and Jetson?"):
                self.log_pi("Shutting down Jetson first...")
                self.send_jetson_command("sudo shutdown now")
                time.sleep(2)
                self.log_pi("Shutting down Pi...")
                os.system("sudo shutdown now")
                
    def open_web_ui(self):
        """Open web UI in browser"""
        import webbrowser
        webbrowser.open(f"http://{PI_IP_ETH}:{WEB_PORT}")
        
    def on_closing(self):
        """Clean shutdown when window closes"""
        self.running = False
        self.stop_system()
        if self.jetson_ssh:
            self.jetson_ssh.close()
        self.root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = NanoOWLController(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
