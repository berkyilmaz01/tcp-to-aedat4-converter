#!/usr/bin/env python3
"""
Demo Fake Camera - High-throughput text display for 10K+ FPS

Renders text like "TYPE1COMPUTE" or "IAI DEMO" as event patterns.
Optimized for maximum throughput with batch sending.

Usage:
    # Maximum throughput with text
    python3 demo_fake_camera.py --text "IAI DEMO" --no-ratelimit --batch 100

    # 10K FPS with scrolling text
    python3 demo_fake_camera.py --text "TYPE1COMPUTE" --mode scroll --fps 10000

    # 10GB transfer with text
    python3 demo_fake_camera.py --text "IAI" --target-gb 10 --no-ratelimit
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
FRAME_SIZE = (TOTAL_PIXELS + 3) // 4
BYTES_PER_GB = 1024 * 1024 * 1024

running = True

def signal_handler(sig, frame):
    global running
    print("\nShutting down...")
    running = False

# Simple 5x7 bitmap font
FONT = {
    'A': ["  #  ", " # # ", "#   #", "#####", "#   #", "#   #", "#   #"],
    'B': ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    'C': [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    'D': ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    'E': ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    'F': ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    'G': [" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ### "],
    'H': ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    'I': ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    'J': ["#####", "    #", "    #", "    #", "#   #", "#   #", " ### "],
    'K': ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    'L': ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    'M': ["#   #", "## ##", "# # #", "#   #", "#   #", "#   #", "#   #"],
    'N': ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    'O': [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    'P': ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    'Q': [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    'R': ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    'S': [" ### ", "#   #", "#    ", " ### ", "    #", "#   #", " ### "],
    'T': ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    'U': ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    'V': ["#   #", "#   #", "#   #", "#   #", " # # ", " # # ", "  #  "],
    'W': ["#   #", "#   #", "#   #", "#   #", "# # #", "## ##", "#   #"],
    'X': ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    'Y': ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    'Z': ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    '0': [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    '1': ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    '2': [" ### ", "#   #", "    #", "  ## ", " #   ", "#    ", "#####"],
    '3': [" ### ", "#   #", "    #", "  ## ", "    #", "#   #", " ### "],
    '4': ["#   #", "#   #", "#   #", "#####", "    #", "    #", "    #"],
    '5': ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    '6': [" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "],
    '7': ["#####", "    #", "   # ", "  #  ", "  #  ", "  #  ", "  #  "],
    '8': [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    '9': [" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "],
    ' ': ["     ", "     ", "     ", "     ", "     ", "     ", "     "],
    '-': ["     ", "     ", "     ", "#####", "     ", "     ", "     "],
    '.': ["     ", "     ", "     ", "     ", "     ", "  #  ", "  #  "],
    '!': ["  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "     ", "  #  "],
}

CHAR_WIDTH = 5
CHAR_HEIGHT = 7
CHAR_SPACING = 1


def set_pixel(data: bytearray, x: int, y: int, polarity: int):
    """Set a pixel in 2-bit packed format."""
    if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
        return
    pixel_index = y * WIDTH + x
    byte_index = pixel_index // 4
    shift = (3 - (pixel_index % 4)) * 2
    mask = ~(0b11 << shift) & 0xFF
    data[byte_index] = (data[byte_index] & mask) | (polarity << shift)


def render_char(data: bytearray, char: str, start_x: int, start_y: int, scale: int, polarity: int):
    """Render a single character at given position with scale."""
    char = char.upper() if char.upper() in FONT else ' '
    bitmap = FONT[char]
    
    for row_idx, row in enumerate(bitmap):
        for col_idx, pixel in enumerate(row):
            if pixel == '#':
                for sy in range(scale):
                    for sx in range(scale):
                        px = start_x + col_idx * scale + sx
                        py = start_y + row_idx * scale + sy
                        set_pixel(data, px, py, polarity)


def render_text(data: bytearray, text: str, start_x: int, start_y: int, scale: int, polarity: int):
    """Render a string of text."""
    x = start_x
    for char in text:
        render_char(data, char, x, start_y, scale, polarity)
        x += (CHAR_WIDTH + CHAR_SPACING) * scale


def get_text_width(text: str, scale: int) -> int:
    """Calculate pixel width of text."""
    return len(text) * (CHAR_WIDTH + CHAR_SPACING) * scale - CHAR_SPACING * scale


def create_wave_frames(text: str, scale: int, num_frames: int) -> list:
    """Pre-generate frames with wavy text animation."""
    text_width = get_text_width(text, scale)
    start_x = (WIDTH - text_width) // 2
    base_y = HEIGHT // 2
    
    frames = []
    for frame_idx in range(num_frames):
        data = bytearray(FRAME_SIZE)
        x = start_x
        for char_idx, char in enumerate(text):
            wave = int(30 * math.sin(2 * math.pi * (frame_idx / 30 + char_idx / 3)))
            y = base_y + wave - (CHAR_HEIGHT * scale) // 2
            polarity = 1 if (char_idx + frame_idx // 15) % 2 == 0 else 2
            render_char(data, char, x, y, scale, polarity)
            x += (CHAR_WIDTH + CHAR_SPACING) * scale
        frames.append(bytes(data))
        if (frame_idx + 1) % 50 == 0:
            print(f"  Generated {frame_idx + 1}/{num_frames} frames")
    return frames


def create_scrolling_frames(text: str, scale: int, num_frames: int) -> list:
    """Pre-generate frames with scrolling text."""
    text_width = get_text_width(text, scale)
    text_height = CHAR_HEIGHT * scale
    start_y = (HEIGHT - text_height) // 2
    total_scroll = WIDTH + text_width
    
    frames = []
    for i in range(num_frames):
        data = bytearray(FRAME_SIZE)
        progress = (i / num_frames) * total_scroll
        x = int(WIDTH - progress)
        polarity = 1 if (i // 30) % 2 == 0 else 2
        render_text(data, text, x, start_y, scale, polarity)
        frames.append(bytes(data))
        if (i + 1) % 50 == 0:
            print(f"  Generated {i + 1}/{num_frames} frames")
    return frames


def create_blink_frames(text: str, scale: int, num_frames: int) -> list:
    """Pre-generate frames with blinking text."""
    text_width = get_text_width(text, scale)
    text_height = CHAR_HEIGHT * scale
    start_x = (WIDTH - text_width) // 2
    start_y = (HEIGHT - text_height) // 2
    
    frames = []
    for i in range(num_frames):
        data = bytearray(FRAME_SIZE)
        polarity = 1 if (i // 20) % 2 == 0 else 2
        render_text(data, text, start_x, start_y, scale, polarity)
        frames.append(bytes(data))
        if (i + 1) % 50 == 0:
            print(f"  Generated {i + 1}/{num_frames} frames")
    return frames


def create_static_frames(text: str, scale: int, num_frames: int) -> list:
    """Pre-generate static text frames."""
    text_width = get_text_width(text, scale)
    text_height = CHAR_HEIGHT * scale
    start_x = (WIDTH - text_width) // 2
    start_y = (HEIGHT - text_height) // 2
    
    data = bytearray(FRAME_SIZE)
    render_text(data, text, start_x, start_y, scale, 1)
    frame = bytes(data)
    
    print(f"  Generated static frame (duplicated {num_frames}x)")
    return [frame] * num_frames


def create_batches(frames: list, batch_size: int) -> list:
    """Concatenate frames into batches for faster sending."""
    batches = []
    for i in range(0, len(frames), batch_size):
        batch = b''.join(frames[i:i+batch_size])
        batches.append(batch)
    return batches


def main():
    global running
    
    parser = argparse.ArgumentParser(description="Demo fake camera - high throughput text display")
    parser.add_argument("--target", type=str, default="127.0.0.1", help="Converter IP")
    parser.add_argument("--port", type=int, default=6000, help="Converter port")
    parser.add_argument("--text", type=str, default="IAI DEMO", help="Text to display")
    parser.add_argument("--scale", type=int, default=8, help="Text scale (default: 8)")
    parser.add_argument("--fps", type=int, default=10000, help="Target FPS (default: 10000)")
    parser.add_argument("--mode", choices=['scroll', 'blink', 'wave', 'static'], 
                        default='wave', help="Animation mode")
    parser.add_argument("--pregenerate", type=int, default=200, help="Frames to pre-generate")
    parser.add_argument("--batch", type=int, default=50, help="Frames per batch (default: 50)")
    parser.add_argument("--target-gb", type=float, default=0, help="Stop after N GB")
    parser.add_argument("--target-frames", type=int, default=0, help="Stop after N frames")
    parser.add_argument("--duration", type=int, default=0, help="Run for N seconds")
    parser.add_argument("--no-ratelimit", action="store_true", help="Send at max speed")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Calculate targets
    target_bytes = 0
    target_frames = args.target_frames
    if args.target_gb > 0:
        target_bytes = int(args.target_gb * BYTES_PER_GB)
        target_frames = (target_bytes + FRAME_SIZE - 1) // FRAME_SIZE

    print(f"\n{'=' * 70}")
    print(f"Demo Fake Camera - High Throughput Text Display")
    print(f"{'=' * 70}")
    print(f"Text: \"{args.text}\"")
    print(f"Scale: {args.scale}x")
    print(f"Mode: {args.mode}")
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"Frame size: {FRAME_SIZE:,} bytes")
    print(f"Batch size: {args.batch} frames")
    print(f"Target: {args.target}:{args.port}")
    print(f"Speed: {'MAX THROUGHPUT' if args.no_ratelimit else f'{args.fps:,} FPS'}")
    if target_bytes > 0:
        print(f"Goal: {args.target_gb} GB ({target_frames:,} frames)")
    if args.duration > 0:
        print(f"Duration: {args.duration} seconds")
    print(f"{'=' * 70}")

    # Pre-generate frames
    print(f"\nPre-generating {args.pregenerate} frames ({args.mode} mode)...")
    
    if args.mode == 'scroll':
        frames = create_scrolling_frames(args.text, args.scale, args.pregenerate)
    elif args.mode == 'blink':
        frames = create_blink_frames(args.text, args.scale, args.pregenerate)
    elif args.mode == 'wave':
        frames = create_wave_frames(args.text, args.scale, args.pregenerate)
    else:
        frames = create_static_frames(args.text, args.scale, args.pregenerate)

    # Create batches for high-throughput sending
    print(f"Creating batches of {args.batch} frames...")
    batches = create_batches(frames, args.batch)
    batch_frames = args.batch
    
    total_mb = sum(len(b) for b in batches) / (1024 * 1024)
    print(f"Created {len(batches)} batches, {total_mb:.1f} MB total")

    # Throughput info
    if not args.no_ratelimit:
        throughput_gbps = (args.fps * FRAME_SIZE * 8) / 1_000_000_000
        print(f"\nTarget throughput: {throughput_gbps:.2f} Gbps")
        if throughput_gbps > 10:
            print(f"WARNING: Exceeds 10GbE capacity!")

    frame_interval = 1.0 / args.fps
    batch_interval = frame_interval * batch_frames

    while running:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        print(f"\nConnecting to {args.target}:{args.port}...")
        
        try:
            sock.connect((args.target, args.port))
            print("Connected! Displaying text...")
            
            # Optimize socket
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 100 * 1024 * 1024)
            except:
                pass

            batch_idx = 0
            total_frames = 0
            total_bytes = 0
            start_time = time.time()
            last_report = start_time

            print(f"\nSending \"{args.text}\" (batch mode)...")
            print("-" * 70)

            while running:
                # Check stop conditions
                if target_frames > 0 and total_frames >= target_frames:
                    print(f"\n>>> Reached target: {total_frames:,} frames")
                    running = False
                    break
                    
                if args.duration > 0 and (time.time() - start_time) >= args.duration:
                    print(f"\n>>> Reached duration: {args.duration} seconds")
                    running = False
                    break

                # Get batch
                batch_data = batches[batch_idx % len(batches)]
                frames_in_batch = len(batch_data) // FRAME_SIZE

                try:
                    sock.sendall(batch_data)
                    
                    batch_idx += 1
                    total_frames += frames_in_batch
                    total_bytes += len(batch_data)

                    # Progress report every 0.5s
                    now = time.time()
                    if now - last_report >= 0.5:
                        elapsed = now - start_time
                        fps = total_frames / elapsed
                        gb_sent = total_bytes / BYTES_PER_GB
                        gbps = (total_bytes * 8) / (elapsed * 1_000_000_000)
                        
                        progress = ""
                        if target_bytes > 0:
                            pct = (total_bytes / target_bytes) * 100
                            eta = (target_bytes - total_bytes) / (total_bytes / elapsed) if total_bytes > 0 else 0
                            progress = f" | {pct:.1f}% (ETA: {eta:.0f}s)"
                        
                        print(f"Frames: {total_frames:>10,} | FPS: {fps:>8,.0f} | "
                              f"Sent: {gb_sent:>6.3f} GB | {gbps:>5.2f} Gbps{progress}")
                        
                        last_report = now

                    # Rate limiting
                    if not args.no_ratelimit:
                        target_time = start_time + batch_idx * batch_interval
                        sleep_time = target_time - time.time()
                        if sleep_time > 0:
                            time.sleep(sleep_time)

                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    print(f"\nConnection lost: {e}")
                    break

            # Final stats
            elapsed = time.time() - start_time
            if elapsed > 0:
                gb_sent = total_bytes / BYTES_PER_GB
                avg_fps = total_frames / elapsed
                gbps = (total_bytes * 8) / (elapsed * 1_000_000_000)
                
                print(f"\n{'=' * 70}")
                print(f"FINAL RESULTS - \"{args.text}\"")
                print(f"{'=' * 70}")
                print(f"Total frames sent:  {total_frames:,}")
                print(f"Total data sent:    {gb_sent:.3f} GB")
                print(f"Duration:           {elapsed:.2f} seconds")
                print(f"Average FPS:        {avg_fps:,.0f}")
                print(f"Average throughput: {gbps:.2f} Gbps")
                print(f"{'=' * 70}")
            
            sock.close()
            
            if target_frames > 0 and total_frames >= target_frames:
                break

        except ConnectionRefusedError:
            print("Connection refused. Is the converter running?")
            print("Retrying in 2 seconds...")
            time.sleep(2)
        except Exception as e:
            if running:
                print(f"Error: {e}")
                time.sleep(2)

    print("\nDemo camera shutdown complete")


if __name__ == "__main__":
    main()
