#!/usr/bin/env python3
"""
Professional Event Camera Viewer

Features:
- Dark theme with color-coded events
- Time surface visualization (events fade over time)
- Multiple view modes (toggle with keys)
- Professional statistics overlay
- Event trails and decay
- Heatmap mode
- Polarity split view

Controls:
    1 - Standard mode (blue/red events)
    2 - Time surface mode (events fade)
    3 - Heatmap mode (activity density)
    4 - Split polarity view
    Q/ESC - Quit
    R - Reset statistics
    S - Screenshot
    SPACE - Pause/Resume

Usage:
    python3 pro_viewer.py
    python3 pro_viewer.py --port 6000 --fps 60
"""

import socket
import numpy as np
import cv2
import signal
import sys
import time
import argparse
from collections import deque
from datetime import datetime

# Settings - must match FPGA
WIDTH = 1280
HEIGHT = 720
FRAME_SIZE = (WIDTH * HEIGHT + 3) // 4
PORT = 6000

# Colors (BGR format for OpenCV)
COLOR_BACKGROUND = (30, 30, 30)       # Dark gray
COLOR_POSITIVE = (255, 180, 50)        # Cyan/Blue for positive (brighter)
COLOR_NEGATIVE = (50, 50, 255)         # Red/Orange for negative (darker)
COLOR_TEXT = (220, 220, 220)           # Light gray
COLOR_TEXT_HIGHLIGHT = (100, 255, 100) # Green
COLOR_TEXT_WARNING = (50, 150, 255)    # Orange
COLOR_PANEL_BG = (45, 45, 45)          # Panel background
COLOR_BORDER = (80, 80, 80)            # Border color

running = True
paused = False

def signal_handler(sig, frame):
    global running
    print("\nExiting...")
    running = False

signal.signal(signal.SIGINT, signal_handler)


class EventVisualizer:
    """Professional event camera visualizer with multiple modes"""
    
    def __init__(self, width, height):
        self.width = width
        self.height = height
        
        # View modes
        self.MODE_STANDARD = 1
        self.MODE_TIME_SURFACE = 2
        self.MODE_HEATMAP = 3
        self.MODE_SPLIT = 4
        self.current_mode = self.MODE_STANDARD
        self.mode_names = {
            1: "Standard",
            2: "Time Surface", 
            3: "Heatmap",
            4: "Split Polarity"
        }
        
        # Time surface state (stores last event time for each pixel)
        self.time_surface_pos = np.zeros((height, width), dtype=np.float32)
        self.time_surface_neg = np.zeros((height, width), dtype=np.float32)
        self.current_time = 0.0
        self.decay_rate = 0.03  # How fast events fade (per frame)
        
        # Heatmap accumulator
        self.heatmap = np.zeros((height, width), dtype=np.float32)
        self.heatmap_decay = 0.95  # Decay factor per frame
        
        # Statistics
        self.frame_count = 0
        self.total_events = 0
        self.events_this_second = 0
        self.events_per_second = 0
        self.last_fps_time = time.time()
        self.fps_frame_count = 0
        self.current_fps = 0.0
        self.start_time = time.time()
        self.events_history = deque(maxlen=100)  # For event rate graph
        
    def reset_stats(self):
        """Reset all statistics"""
        self.frame_count = 0
        self.total_events = 0
        self.events_this_second = 0
        self.events_per_second = 0
        self.last_fps_time = time.time()
        self.fps_frame_count = 0
        self.current_fps = 0.0
        self.start_time = time.time()
        self.events_history.clear()
        self.heatmap.fill(0)
        self.time_surface_pos.fill(0)
        self.time_surface_neg.fill(0)
        
    def unpack_frame(self, data):
        """Unpack 2-bit packed frame and extract event locations"""
        # Convert to numpy array
        arr = np.frombuffer(data, dtype=np.uint8)
        
        # Extract 4 pixels from each byte
        p0 = (arr >> 6) & 0x03
        p1 = (arr >> 4) & 0x03
        p2 = (arr >> 2) & 0x03
        p3 = arr & 0x03
        
        # Interleave pixels
        pixels = np.empty(len(arr) * 4, dtype=np.uint8)
        pixels[0::4] = p0
        pixels[1::4] = p1
        pixels[2::4] = p2
        pixels[3::4] = p3
        
        # Trim to resolution
        pixels = pixels[:self.width * self.height]
        pixels = pixels.reshape((self.height, self.width))
        
        # Find positive and negative events
        pos_mask = (pixels == 1)
        neg_mask = (pixels == 2)
        
        return pos_mask, neg_mask
    
    def process_frame(self, data):
        """Process a frame and update internal state"""
        pos_mask, neg_mask = self.unpack_frame(data)
        
        # Count events
        num_pos = np.sum(pos_mask)
        num_neg = np.sum(neg_mask)
        num_events = num_pos + num_neg
        
        # Update statistics
        self.frame_count += 1
        self.total_events += num_events
        self.events_this_second += num_events
        self.fps_frame_count += 1
        
        # Calculate FPS every second
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        if elapsed >= 1.0:
            self.current_fps = self.fps_frame_count / elapsed
            self.events_per_second = self.events_this_second / elapsed
            self.events_history.append(self.events_per_second)
            self.fps_frame_count = 0
            self.events_this_second = 0
            self.last_fps_time = current_time
        
        # Update time surface
        self.current_time += 1
        self.time_surface_pos[pos_mask] = self.current_time
        self.time_surface_neg[neg_mask] = self.current_time
        
        # Update heatmap
        self.heatmap *= self.heatmap_decay
        self.heatmap[pos_mask] += 1.0
        self.heatmap[neg_mask] += 1.0
        
        return pos_mask, neg_mask, num_events
    
    def render_standard(self, pos_mask, neg_mask):
        """Render standard view with colored events"""
        img = np.full((self.height, self.width, 3), COLOR_BACKGROUND, dtype=np.uint8)
        img[pos_mask] = COLOR_POSITIVE
        img[neg_mask] = COLOR_NEGATIVE
        return img
    
    def render_time_surface(self):
        """Render time surface view where events fade over time"""
        img = np.full((self.height, self.width, 3), COLOR_BACKGROUND, dtype=np.uint8)
        
        # Calculate age of events (0 = new, 1 = old)
        age_pos = np.clip((self.current_time - self.time_surface_pos) * self.decay_rate, 0, 1)
        age_neg = np.clip((self.current_time - self.time_surface_neg) * self.decay_rate, 0, 1)
        
        # Only show events that aren't too old
        pos_visible = (self.time_surface_pos > 0) & (age_pos < 1)
        neg_visible = (self.time_surface_neg > 0) & (age_neg < 1)
        
        # Interpolate colors based on age (bright when new, fade to background)
        for c in range(3):
            img[:,:,c][pos_visible] = (
                COLOR_POSITIVE[c] * (1 - age_pos[pos_visible]) + 
                COLOR_BACKGROUND[c] * age_pos[pos_visible]
            ).astype(np.uint8)
            
            img[:,:,c][neg_visible] = (
                COLOR_NEGATIVE[c] * (1 - age_neg[neg_visible]) + 
                COLOR_BACKGROUND[c] * age_neg[neg_visible]
            ).astype(np.uint8)
        
        return img
    
    def render_heatmap(self):
        """Render heatmap view showing activity density"""
        # Normalize heatmap
        max_val = max(np.max(self.heatmap), 1)
        normalized = np.clip(self.heatmap / max_val, 0, 1)
        
        # Apply colormap (COLORMAP_JET or COLORMAP_HOT)
        heatmap_uint8 = (normalized * 255).astype(np.uint8)
        img = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)
        
        # Make background darker
        mask = (self.heatmap < 0.01)
        img[mask] = COLOR_BACKGROUND
        
        return img
    
    def render_split(self, pos_mask, neg_mask):
        """Render split view with positive and negative side by side"""
        half_width = self.width // 2
        
        img = np.full((self.height, self.width, 3), COLOR_BACKGROUND, dtype=np.uint8)
        
        # Left side: positive events
        pos_img = np.full((self.height, half_width, 3), (40, 40, 40), dtype=np.uint8)
        pos_resized = cv2.resize(pos_mask.astype(np.uint8) * 255, (half_width, self.height))
        pos_img[pos_resized > 0] = COLOR_POSITIVE
        img[:, :half_width] = pos_img
        
        # Right side: negative events
        neg_img = np.full((self.height, half_width, 3), (40, 40, 40), dtype=np.uint8)
        neg_resized = cv2.resize(neg_mask.astype(np.uint8) * 255, (half_width, self.height))
        neg_img[neg_resized > 0] = COLOR_NEGATIVE
        img[:, half_width:] = neg_img
        
        # Divider line
        cv2.line(img, (half_width, 0), (half_width, self.height), COLOR_BORDER, 2)
        
        # Labels
        cv2.putText(img, "POSITIVE (ON)", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_POSITIVE, 2)
        cv2.putText(img, "NEGATIVE (OFF)", (half_width + 10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_NEGATIVE, 2)
        
        return img
    
    def render(self, data):
        """Main render function - processes frame and renders current mode"""
        pos_mask, neg_mask, num_events = self.process_frame(data)
        
        # Render based on current mode
        if self.current_mode == self.MODE_STANDARD:
            img = self.render_standard(pos_mask, neg_mask)
        elif self.current_mode == self.MODE_TIME_SURFACE:
            img = self.render_time_surface()
        elif self.current_mode == self.MODE_HEATMAP:
            img = self.render_heatmap()
        elif self.current_mode == self.MODE_SPLIT:
            img = self.render_split(pos_mask, neg_mask)
        else:
            img = self.render_standard(pos_mask, neg_mask)
        
        return img, num_events
    
    def draw_stats_overlay(self, img):
        """Draw professional statistics overlay"""
        # Panel dimensions
        panel_width = 320
        panel_height = 200
        margin = 10
        
        # Create semi-transparent panel
        overlay = img.copy()
        cv2.rectangle(overlay, 
                     (margin, margin), 
                     (margin + panel_width, margin + panel_height),
                     COLOR_PANEL_BG, -1)
        cv2.rectangle(overlay,
                     (margin, margin),
                     (margin + panel_width, margin + panel_height),
                     COLOR_BORDER, 1)
        
        # Blend with original
        alpha = 0.85
        img = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)
        
        # Title bar
        cv2.rectangle(img, (margin, margin), (margin + panel_width, margin + 28), 
                     (60, 60, 60), -1)
        cv2.putText(img, "EVENT CAMERA VIEWER", (margin + 10, margin + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_TEXT_HIGHLIGHT, 1)
        
        # Mode indicator
        mode_text = f"[{self.current_mode}] {self.mode_names.get(self.current_mode, 'Unknown')}"
        cv2.putText(img, mode_text, (margin + 200, margin + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_TEXT, 1)
        
        # Statistics
        y_offset = margin + 50
        line_height = 22
        
        stats = [
            ("Frame", f"{self.frame_count:,}"),
            ("FPS", f"{self.current_fps:.1f}"),
            ("Events/sec", f"{self.events_per_second/1000:.1f}K" if self.events_per_second >= 1000 
                          else f"{self.events_per_second:.0f}"),
            ("Total Events", f"{self.total_events/1000000:.2f}M" if self.total_events >= 1000000
                            else f"{self.total_events/1000:.1f}K" if self.total_events >= 1000
                            else f"{self.total_events}"),
            ("Runtime", self._format_runtime()),
        ]
        
        for label, value in stats:
            cv2.putText(img, f"{label}:", (margin + 15, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1)
            cv2.putText(img, str(value), (margin + 140, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT_HIGHLIGHT, 1)
            y_offset += line_height
        
        # Event rate mini-graph
        if len(self.events_history) > 1:
            self._draw_mini_graph(img, margin + 15, y_offset + 5, 
                                 panel_width - 30, 35, self.events_history)
        
        # Controls hint at bottom
        hint_y = self.height - 25
        cv2.rectangle(img, (0, hint_y - 5), (self.width, self.height), (40, 40, 40), -1)
        cv2.putText(img, "[1-4] View Mode | [R] Reset | [S] Screenshot | [SPACE] Pause | [Q] Quit",
                   (10, hint_y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_TEXT, 1)
        
        return img
    
    def _format_runtime(self):
        """Format runtime as HH:MM:SS"""
        elapsed = int(time.time() - self.start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def _draw_mini_graph(self, img, x, y, width, height, data):
        """Draw a mini line graph of event rate history"""
        if len(data) < 2:
            return
        
        # Background
        cv2.rectangle(img, (x, y), (x + width, y + height), (50, 50, 50), -1)
        cv2.rectangle(img, (x, y), (x + width, y + height), COLOR_BORDER, 1)
        
        # Normalize data
        data_arr = np.array(list(data))
        max_val = max(np.max(data_arr), 1)
        normalized = data_arr / max_val
        
        # Draw line
        points = []
        for i, val in enumerate(normalized):
            px = x + int(i * width / len(normalized))
            py = y + height - int(val * (height - 4)) - 2
            points.append((px, py))
        
        for i in range(len(points) - 1):
            cv2.line(img, points[i], points[i+1], COLOR_TEXT_HIGHLIGHT, 1)
        
        # Label
        cv2.putText(img, "Event Rate", (x + 5, y + 12),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, COLOR_TEXT, 1)


def main():
    global running, paused
    
    parser = argparse.ArgumentParser(description="Professional Event Camera Viewer")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    parser.add_argument("--fps", type=int, default=60, help="Target display FPS (default: 60)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("   PROFESSIONAL EVENT CAMERA VIEWER")
    print("=" * 60)
    print(f"   Resolution: {WIDTH}x{HEIGHT}")
    print(f"   Port: {args.port}")
    print(f"   Display FPS: {args.fps}")
    print("=" * 60)
    print()
    print("   Controls:")
    print("     1-4  : Switch view mode")
    print("     R    : Reset statistics")
    print("     S    : Save screenshot")
    print("     SPACE: Pause/Resume")
    print("     Q/ESC: Quit")
    print()
    print("   Waiting for connection...")
    print()
    
    # Create visualizer
    visualizer = EventVisualizer(WIDTH, HEIGHT)
    
    # Create TCP server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1.0)
    
    try:
        server.bind(("0.0.0.0", args.port))
        server.listen(1)
        print(f"   Listening on port {args.port}...")
        
        client = None
        while running and client is None:
            try:
                client, addr = server.accept()
                print(f"   Connected: {addr}")
                client.settimeout(0.1)
            except socket.timeout:
                continue
        
        if client is None:
            return
        
        # Create window
        cv2.namedWindow("Event Camera Viewer", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Event Camera Viewer", WIDTH, HEIGHT)
        
        buffer = b""
        display_interval = 1.0 / args.fps
        last_display_time = time.time()
        
        while running:
            try:
                if not paused:
                    # Receive data
                    chunk = client.recv(262144)
                    if not chunk:
                        print("Connection closed")
                        break
                    
                    buffer += chunk
                    
                    # Process frames
                    while len(buffer) >= FRAME_SIZE:
                        frame_data = buffer[:FRAME_SIZE]
                        buffer = buffer[FRAME_SIZE:]
                        
                        # Only render at target FPS
                        current_time = time.time()
                        if current_time - last_display_time >= display_interval:
                            # Render frame
                            img, num_events = visualizer.render(frame_data)
                            
                            # Add stats overlay
                            img = visualizer.draw_stats_overlay(img)
                            
                            # Add pause indicator
                            if paused:
                                cv2.putText(img, "PAUSED", (WIDTH//2 - 80, HEIGHT//2),
                                           cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
                            
                            cv2.imshow("Event Camera Viewer", img)
                            last_display_time = current_time
                
                # Handle key presses
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q') or key == 27:  # Q or ESC
                    running = False
                elif key == ord('1'):
                    visualizer.current_mode = visualizer.MODE_STANDARD
                    print("Mode: Standard")
                elif key == ord('2'):
                    visualizer.current_mode = visualizer.MODE_TIME_SURFACE
                    print("Mode: Time Surface")
                elif key == ord('3'):
                    visualizer.current_mode = visualizer.MODE_HEATMAP
                    print("Mode: Heatmap")
                elif key == ord('4'):
                    visualizer.current_mode = visualizer.MODE_SPLIT
                    print("Mode: Split Polarity")
                elif key == ord('r'):
                    visualizer.reset_stats()
                    print("Statistics reset")
                elif key == ord('s'):
                    # Screenshot
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"screenshot_{timestamp}.png"
                    cv2.imwrite(filename, img)
                    print(f"Screenshot saved: {filename}")
                elif key == ord(' '):
                    paused = not paused
                    print("Paused" if paused else "Resumed")
                    
            except socket.timeout:
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    running = False
                elif key == ord(' '):
                    paused = not paused
                continue
            except Exception as e:
                print(f"Error: {e}")
                break
        
        client.close()
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        server.close()
        cv2.destroyAllWindows()
        
        # Final stats
        print()
        print("=" * 60)
        print("   SESSION SUMMARY")
        print("=" * 60)
        print(f"   Total Frames: {visualizer.frame_count:,}")
        print(f"   Total Events: {visualizer.total_events:,}")
        print(f"   Avg Events/Frame: {visualizer.total_events/max(visualizer.frame_count,1):.1f}")
        print(f"   Runtime: {visualizer._format_runtime()}")
        print("=" * 60)


if __name__ == "__main__":
    main()
