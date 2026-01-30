#!/usr/bin/env python3
"""
Fake Camera Simulator - Basic TCP test for converter

Generates moving circle patterns in 2-bit packed FPGA format.
Use this for quick testing of the converter pipeline.

Usage:
    python3 fake_camera.py              # Default: 100 FPS, port 6000
    python3 fake_camera.py --fps 50     # Custom frame rate
    python3 fake_camera.py --port 6001  # Custom port

Data Format:
    2-bit packed pixels (4 pixels per byte, MSB first)
    00 = no event, 01 = positive, 10 = negative
"""

import socket
import time
import argparse
import signal
import sys
import math

# Frame configuration (matches FPGA 2-bit format)
WIDTH = 1280
HEIGHT = 720
TOTAL_PIXELS = WIDTH * HEIGHT
FRAME_SIZE = (TOTAL_PIXELS + 3) // 4  # 230,400 bytes

running = True


def signal_handler(sig, frame):
    global running
    print("\nShutting down...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def set_pixel(data: bytearray, x: int, y: int, polarity: int):
    """
    Set a pixel in 2-bit packed format.
    
    Args:
        data: Frame buffer
        x, y: Pixel coordinates
        polarity: 1 = positive (brightness increased), 2 = negative (brightness decreased)
    """
    if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
        return
    pixel_index = y * WIDTH + x
    byte_index = pixel_index // 4
    shift = (3 - (pixel_index % 4)) * 2
    mask = ~(0b11 << shift) & 0xFF
    data[byte_index] = (data[byte_index] & mask) | (polarity << shift)


def draw_circle(data: bytearray, cx: int, cy: int, radius: int, polarity: int):
    """Draw a filled circle."""
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        y = cy + dy
        if 0 <= y < HEIGHT:
            dx_max = int(math.sqrt(max(0, r2 - dy * dy)))
            for dx in range(-dx_max, dx_max + 1):
                x = cx + dx
                if 0 <= x < WIDTH:
                    set_pixel(data, x, y, polarity)


def create_frame(frame_num: int) -> bytes:
    """
    Create a frame with two moving circles.
    
    - Positive polarity circle moves horizontally
    - Negative polarity circle moves vertically
    """
    data = bytearray(FRAME_SIZE)
    
    radius = 40
    
    # Positive circle - horizontal motion
    period_x = 200
    cx_pos = int(WIDTH / 2 + (WIDTH / 3) * math.sin(2 * math.pi * frame_num / period_x))
    cy_pos = HEIGHT // 3
    draw_circle(data, cx_pos, cy_pos, radius, 1)  # polarity = 1 (positive)
    
    # Negative circle - vertical motion
    period_y = 150
    cx_neg = WIDTH // 2
    cy_neg = int(HEIGHT / 2 + (HEIGHT / 3) * math.sin(2 * math.pi * frame_num / period_y))
    draw_circle(data, cx_neg, cy_neg, radius, 2)  # polarity = 2 (negative)
    
    return bytes(data)


def main():
    global running
    
    parser = argparse.ArgumentParser(
        description="Fake Camera Simulator - generates test patterns for converter"
    )
    parser.add_argument("--target", type=str, default="127.0.0.1",
                        help="Converter IP address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=6000,
                        help="Converter port (default: 6000)")
    parser.add_argument("--fps", type=int, default=100,
                        help="Target frame rate (default: 100)")
    args = parser.parse_args()
    
    frame_interval = 1.0 / args.fps
    
    print("=" * 60)
    print("  Fake Camera Simulator (2-bit FPGA format)")
    print("=" * 60)
    print(f"  Resolution: {WIDTH}x{HEIGHT}")
    print(f"  Frame size: {FRAME_SIZE:,} bytes (2-bit packed)")
    print(f"  Target: {args.target}:{args.port}")
    print(f"  Target FPS: {args.fps}")
    print("=" * 60)
    print()
    
    # Pre-generate some frames for smoother playback
    print("Pre-generating frames...")
    num_pregenerate = min(args.fps * 2, 500)  # 2 seconds or 500 frames max
    frames = [create_frame(i) for i in range(num_pregenerate)]
    print(f"Generated {len(frames)} frames")
    print()
    
    while running:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        print(f"Connecting to converter at {args.target}:{args.port}...")
        
        try:
            sock.connect((args.target, args.port))
            print("Connected!")
            print("Streaming frames... (Ctrl+C to stop)")
            print()
            
            # Optimize socket for throughput
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            frame_idx = 0
            start_time = time.time()
            last_report = start_time
            
            while running:
                loop_start = time.time()
                
                # Send frame
                frame = frames[frame_idx % len(frames)]
                sock.sendall(frame)
                
                frame_idx += 1
                
                # Report stats every second
                now = time.time()
                if now - last_report >= 1.0:
                    elapsed = now - start_time
                    actual_fps = frame_idx / elapsed
                    mbps = (frame_idx * FRAME_SIZE * 8) / (elapsed * 1_000_000)
                    print(f"Frames: {frame_idx:,} | FPS: {actual_fps:.1f} | Throughput: {mbps:.1f} Mbps")
                    last_report = now
                
                # Pace to target FPS
                elapsed = time.time() - loop_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except ConnectionRefusedError:
            print("Connection refused. Is the converter running?")
            print("Start the converter first: ./converter")
            print("Retrying in 3 seconds...")
            time.sleep(3)
        except BrokenPipeError:
            print("Connection lost (converter disconnected)")
            if running:
                print("Retrying in 2 seconds...")
                time.sleep(2)
        except Exception as e:
            if running:
                print(f"Error: {e}")
                time.sleep(2)
        finally:
            sock.close()
    
    print("\nFake camera stopped.")


if __name__ == "__main__":
    main()
