#!/usr/bin/env python3
"""
Fake Camera Simulator for TCP-to-AEDAT4 Converter Testing

Generates binary frames with 2-bit packed pixel format matching the FPGA output.
This simulates the FPGA/ZCU board that CONNECTS TO the converter.

The FPGA acts as a CLIENT - it connects to the converter (server).
This matches the real FPGA behavior.

Frame format (matches FPGA):
  - Each pixel = 2 bits
  - 4 pixels per byte, MSB first:
    Byte: [pixel0:2][pixel1:2][pixel2:2][pixel3:2]
          bits 7-6   bits 5-4   bits 3-2   bits 1-0
  - Pixel values:
    00 = no event
    01 = positive polarity (p=1)
    10 = negative polarity (p=0)
    11 = unused

Usage:
    python3 fake_camera.py [--target 127.0.0.1] [--port 6000] [--fps 100]
"""

import socket
import time
import argparse
import signal
import sys
import math

# Frame configuration (must match config.hpp and FPGA)
WIDTH = 1280
HEIGHT = 720
TOTAL_PIXELS = WIDTH * HEIGHT                    # 921,600 pixels
FRAME_SIZE = (TOTAL_PIXELS + 3) // 4             # 230,400 bytes (2 bits per pixel)

# Running flag for graceful shutdown
running = True

def signal_handler(sig, frame):
    global running
    print("\nShutting down...")
    running = False


def set_pixel(data: bytearray, x: int, y: int, polarity: int):
    """
    Set a pixel value in the 2-bit packed frame.
    
    Args:
        data: Frame buffer (bytearray)
        x: X coordinate (0 to WIDTH-1)
        y: Y coordinate (0 to HEIGHT-1)
        polarity: 0=no event, 1=positive, 2=negative
    
    Encoding (matches FPGA set_pixel function):
        pixel_index = y * WIDTH + x
        byte_index = pixel_index // 4
        shift = (3 - (pixel_index % 4)) * 2
        
        Bits 7-6 = pixel 0, bits 5-4 = pixel 1, bits 3-2 = pixel 2, bits 1-0 = pixel 3
    """
    if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
        return
    
    pixel_index = y * WIDTH + x
    byte_index = pixel_index // 4
    bit_position = pixel_index % 4
    shift = (3 - bit_position) * 2  # MSB first: positions 0,1,2,3 map to shifts 6,4,2,0
    
    # Clear the 2 bits for this pixel and set new value
    mask = ~(0b11 << shift) & 0xFF
    data[byte_index] = (data[byte_index] & mask) | (polarity << shift)


def create_moving_pattern_frame(frame_num: int) -> bytes:
    """
    Create a frame with moving circle patterns.
    
    Positive circle: moves horizontally
    Negative circle: moves vertically
    
    Returns:
        Frame data as bytes
    """
    data = bytearray(FRAME_SIZE)
    
    # Circle parameters
    radius = 40
    
    # Positive circle: moves horizontally across the screen
    period_x = 200  # frames for one cycle
    cx_pos = int(WIDTH/2 + (WIDTH/3) * math.sin(2 * math.pi * frame_num / period_x))
    cy_pos = HEIGHT // 3
    
    # Draw positive circle (polarity = 1)
    for y in range(max(0, cy_pos - radius), min(HEIGHT, cy_pos + radius + 1)):
        for x in range(max(0, cx_pos - radius), min(WIDTH, cx_pos + radius + 1)):
            dx = x - cx_pos
            dy = y - cy_pos
            if dx*dx + dy*dy <= radius*radius:
                set_pixel(data, x, y, 1)  # positive = 01
    
    # Negative circle: moves vertically
    period_y = 150
    cx_neg = WIDTH // 2
    cy_neg = int(HEIGHT/2 + (HEIGHT/3) * math.sin(2 * math.pi * frame_num / period_y))
    
    # Draw negative circle (polarity = 2)
    for y in range(max(0, cy_neg - radius), min(HEIGHT, cy_neg + radius + 1)):
        for x in range(max(0, cx_neg - radius), min(WIDTH, cx_neg + radius + 1)):
            dx = x - cx_neg
            dy = y - cy_neg
            if dx*dx + dy*dy <= radius*radius:
                # Don't overwrite positive events
                pixel_index = y * WIDTH + x
                byte_index = pixel_index // 4
                bit_position = pixel_index % 4
                shift = (3 - bit_position) * 2
                current_val = (data[byte_index] >> shift) & 0b11
                if current_val == 0:  # Only set if no event yet
                    set_pixel(data, x, y, 2)  # negative = 10
    
    return bytes(data)


def main():
    global running
    
    parser = argparse.ArgumentParser(description="Fake camera simulator (2-bit format) - connects to converter")
    parser.add_argument("--target", type=str, default="127.0.0.1", help="Converter IP address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=6000, help="Converter port (default: 6000)")
    parser.add_argument("--fps", type=int, default=100, help="Frames per second (default: 100)")
    args = parser.parse_args()

    # Validate FPS argument
    if args.fps <= 0:
        print(f"Error: --fps must be a positive integer, got {args.fps}", file=sys.stderr)
        sys.exit(1)

    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"=" * 50)
    print(f"Fake Camera Simulator (2-bit FPGA format)")
    print(f"=" * 50)
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"Frame size: {FRAME_SIZE} bytes (2-bit packed)")
    print(f"Target: {args.target}:{args.port}")
    print(f"Target FPS: {args.fps}")
    print(f"Mode: CLIENT (connects to converter, like real FPGA)")
    print(f"=" * 50)

    frame_interval = 1.0 / args.fps

    while running:
        # Create TCP socket and connect to converter
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        print(f"\nConnecting to converter at {args.target}:{args.port}...")
        
        try:
            client_socket.connect((args.target, args.port))
            print("Connected!")
            
            # Set TCP_NODELAY for lower latency
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            frame_num = 0
            start_time = time.time()

            while running:
                # Generate frame in 2-bit packed format
                frame_data = create_moving_pattern_frame(frame_num)

                try:
                    # Send raw frame data (no header, matches FPGA)
                    client_socket.sendall(frame_data)

                    frame_num += 1

                    # Print stats every 100 frames
                    if frame_num % 100 == 0:
                        elapsed = time.time() - start_time
                        actual_fps = frame_num / elapsed if elapsed > 0 else 0
                        throughput_mbps = (frame_num * FRAME_SIZE * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0
                        print(f"Sent {frame_num} frames | FPS: {actual_fps:.1f} | Throughput: {throughput_mbps:.1f} Mbps")

                    # Rate limiting
                    target_time = start_time + frame_num * frame_interval
                    sleep_time = target_time - time.time()
                    if sleep_time > 0:
                        time.sleep(sleep_time)

                except (BrokenPipeError, ConnectionResetError):
                    print("Connection lost")
                    break

            client_socket.close()

        except ConnectionRefusedError:
            print(f"Connection refused. Is the converter running?")
            print("Retrying in 2 seconds...")
            time.sleep(2)
        except Exception as e:
            if running:
                print(f"Error: {e}")
                print("Retrying in 2 seconds...")
                time.sleep(2)

    print("Fake camera shutdown complete")


if __name__ == "__main__":
    main()
