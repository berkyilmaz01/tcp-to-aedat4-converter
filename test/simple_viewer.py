#!/usr/bin/env python3
"""
Simple Event Viewer - No dv-processing required!

This viewer connects to the fake camera directly and visualizes the 2-bit packed frames.
It bypasses the converter entirely for testing/visualization purposes.

Handles up to 10K+ FPS by displaying only every Nth frame.

Usage:
    python3 simple_viewer.py
    python3 simple_viewer.py --display-fps 60
"""

import socket
import numpy as np
import cv2
import signal
import sys
import time
import argparse

# Settings - must match FPGA/fake camera
WIDTH = 1280
HEIGHT = 720
FRAME_SIZE = (WIDTH * HEIGHT + 3) // 4
PORT = 6000  # Same as fake camera sends to

running = True

def signal_handler(sig, frame):
    global running
    print("\nExiting...")
    running = False

signal.signal(signal.SIGINT, signal_handler)


def unpack_frame(data):
    """Unpack 2-bit packed frame to visualization image (optimized with numpy)"""
    # Convert to numpy array
    arr = np.frombuffer(data, dtype=np.uint8)
    
    # Extract 4 pixels from each byte using vectorized operations
    p0 = (arr >> 6) & 0x03  # First pixel (bits 7-6)
    p1 = (arr >> 4) & 0x03  # Second pixel (bits 5-4)
    p2 = (arr >> 2) & 0x03  # Third pixel (bits 3-2)
    p3 = arr & 0x03         # Fourth pixel (bits 1-0)
    
    # Interleave pixels: [p0[0], p1[0], p2[0], p3[0], p0[1], p1[1], ...]
    pixels = np.empty(len(arr) * 4, dtype=np.uint8)
    pixels[0::4] = p0
    pixels[1::4] = p1
    pixels[2::4] = p2
    pixels[3::4] = p3
    
    # Trim to exact resolution
    pixels = pixels[:WIDTH * HEIGHT]
    
    # Map values: 0->128 (gray), 1->255 (white), 2->0 (black), 3->128 (gray)
    lut = np.array([128, 255, 0, 128], dtype=np.uint8)
    img = lut[pixels]
    
    # Reshape to image
    img = img.reshape((HEIGHT, WIDTH))
    
    return img


def main():
    global running
    
    parser = argparse.ArgumentParser(description="Simple Event Viewer for 10K+ FPS")
    parser.add_argument("--display-fps", type=int, default=60, help="Target display FPS (default: 60)")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to listen on (default: {PORT})")
    args = parser.parse_args()
    
    display_fps = args.display_fps
    port = args.port
    
    print("=" * 60)
    print("Simple Event Viewer (10K+ FPS capable)")
    print("=" * 60)
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"Frame size: {FRAME_SIZE} bytes")
    print(f"Listening on port: {port}")
    print(f"Display target: {display_fps} FPS")
    print("=" * 60)
    print()
    print("This viewer acts as a TCP SERVER.")
    print("Run the fake camera to send frames here.")
    print()
    print("Press 'q' or ESC to quit")
    print()
    
    # Create TCP server socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1.0)
    
    try:
        server.bind(("0.0.0.0", port))
        server.listen(1)
        print(f"Waiting for connection on port {port}...")
        
        client = None
        while running and client is None:
            try:
                client, addr = server.accept()
                print(f"Connected: {addr}")
                client.settimeout(0.1)  # Short timeout for responsiveness
            except socket.timeout:
                continue
        
        if client is None:
            return
        
        # Create window
        cv2.namedWindow("Event Viewer", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Event Viewer", 1280, 720)
        
        # Statistics
        frame_count = 0
        display_count = 0
        buffer = b""
        
        # FPS calculation
        fps_start_time = time.time()
        fps_frame_count = 0
        current_fps = 0.0
        
        # Display timing
        display_interval = 1.0 / display_fps
        last_display_time = time.time()
        
        while running:
            try:
                # Receive data (non-blocking style with short timeout)
                chunk = client.recv(262144)  # 256KB buffer for high throughput
                if not chunk:
                    print("Connection closed")
                    break
                
                buffer += chunk
                
                # Process complete frames
                frames_this_batch = 0
                while len(buffer) >= FRAME_SIZE:
                    frame_data = buffer[:FRAME_SIZE]
                    buffer = buffer[FRAME_SIZE:]
                    
                    frame_count += 1
                    fps_frame_count += 1
                    frames_this_batch += 1
                    
                    # Only display at target FPS
                    current_time = time.time()
                    if current_time - last_display_time >= display_interval:
                        # Unpack and display this frame
                        img = unpack_frame(frame_data)
                        
                        # Add stats overlay
                        cv2.putText(img, f"Frame: {frame_count}", (10, 30),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                        cv2.putText(img, f"Receive FPS: {current_fps:.0f}", (10, 60),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        cv2.putText(img, f"Display FPS: {display_fps}", (10, 90),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
                        cv2.putText(img, f"Buffer: {len(buffer)//1024}KB", (10, 120),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
                        
                        cv2.imshow("Event Viewer", img)
                        display_count += 1
                        last_display_time = current_time
                        
                        # Check for key press
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q') or key == 27:
                            running = False
                            break
                
                # Calculate FPS every second
                elapsed = time.time() - fps_start_time
                if elapsed >= 1.0:
                    current_fps = fps_frame_count / elapsed
                    print(f"Receiving: {current_fps:.0f} FPS | Total: {frame_count} | Buffer: {len(buffer)//1024}KB")
                    fps_frame_count = 0
                    fps_start_time = time.time()
                    
            except socket.timeout:
                # Still check for display/key even when no data
                current_time = time.time()
                if current_time - last_display_time >= display_interval:
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q') or key == 27:
                        break
                    last_display_time = current_time
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
        print(f"Total frames received: {frame_count}")
        print(f"Total frames displayed: {display_count}")
        print("=" * 60)


if __name__ == "__main__":
    main()
