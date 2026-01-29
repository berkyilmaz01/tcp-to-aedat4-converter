#!/usr/bin/env python3
"""
Ultra-Fast Fake Camera - Optimized for 10K+ FPS testing

Pre-generates frames and sends with minimal overhead.
Uses batch sending and memory optimization for maximum throughput.

Target: 10,000+ FPS = 2.3 GB/s = 18.4 Gbps (requires 25GbE or faster)

Usage:
    # Maximum speed test
    python3 fast_fake_camera.py --target-gb 10 --no-ratelimit --batch 100

    # 10K FPS test
    python3 fast_fake_camera.py --fps 10000 --duration 60
"""

import socket
import time
import argparse
import signal
import sys
import math
import os

# Frame configuration (matches FPGA 2-bit format)
WIDTH = 1280
HEIGHT = 720
TOTAL_PIXELS = WIDTH * HEIGHT                    # 921,600 pixels
FRAME_SIZE = (TOTAL_PIXELS + 3) // 4             # 230,400 bytes

BYTES_PER_GB = 1024 * 1024 * 1024

running = True

def signal_handler(sig, frame):
    global running
    print("\nShutting down...")
    running = False


def set_pixel_fast(data: bytearray, pixel_index: int, polarity: int):
    """Fast pixel set without bounds checking."""
    byte_index = pixel_index >> 2
    shift = (3 - (pixel_index & 3)) << 1
    data[byte_index] = (data[byte_index] & ~(0b11 << shift)) | (polarity << shift)


def create_frame_fast(frame_num: int, radius: int = 40) -> bytes:
    """Create a frame with moving circles - optimized."""
    data = bytearray(FRAME_SIZE)
    
    # Positive circle position
    period_x = 200
    cx_pos = int(WIDTH/2 + (WIDTH/3) * math.sin(2 * math.pi * frame_num / period_x))
    cy_pos = HEIGHT // 3
    
    # Negative circle position  
    period_y = 150
    cx_neg = WIDTH // 2
    cy_neg = int(HEIGHT/2 + (HEIGHT/3) * math.sin(2 * math.pi * frame_num / period_y))
    
    r2 = radius * radius
    
    # Draw positive circle
    for dy in range(-radius, radius + 1):
        y = cy_pos + dy
        if 0 <= y < HEIGHT:
            dx_max = int(math.sqrt(max(0, r2 - dy*dy)))
            for dx in range(-dx_max, dx_max + 1):
                x = cx_pos + dx
                if 0 <= x < WIDTH:
                    set_pixel_fast(data, y * WIDTH + x, 1)
    
    # Draw negative circle
    for dy in range(-radius, radius + 1):
        y = cy_neg + dy
        if 0 <= y < HEIGHT:
            dx_max = int(math.sqrt(max(0, r2 - dy*dy)))
            for dx in range(-dx_max, dx_max + 1):
                x = cx_neg + dx
                if 0 <= x < WIDTH:
                    pixel_idx = y * WIDTH + x
                    byte_idx = pixel_idx >> 2
                    shift = (3 - (pixel_idx & 3)) << 1
                    if ((data[byte_idx] >> shift) & 0b11) == 0:
                        data[byte_idx] |= (2 << shift)
    
    return bytes(data)


def pregenerate_frames(num_frames: int) -> bytes:
    """Pre-generate frames and concatenate into single buffer for batch sending."""
    print(f"Pre-generating {num_frames} frames...")
    
    frames_list = []
    for i in range(num_frames):
        frames_list.append(create_frame_fast(i))
        if (i + 1) % 50 == 0:
            print(f"  Generated {i + 1}/{num_frames} frames")
    
    # Concatenate all frames into single bytes object for efficient sending
    all_frames = b''.join(frames_list)
    
    total_mb = len(all_frames) / (1024 * 1024)
    print(f"Pre-generation complete: {num_frames} frames, {total_mb:.1f} MB")
    
    return all_frames, num_frames


def pregenerate_batch(num_frames: int, batch_size: int) -> tuple:
    """Pre-generate frames in batches for ultra-fast sending."""
    print(f"Pre-generating {num_frames} frames in batches of {batch_size}...")
    
    frames_list = []
    for i in range(num_frames):
        frames_list.append(create_frame_fast(i))
        if (i + 1) % 50 == 0:
            print(f"  Generated {i + 1}/{num_frames} frames")
    
    # Create batched buffers
    batches = []
    for i in range(0, num_frames, batch_size):
        batch = b''.join(frames_list[i:i+batch_size])
        batches.append(batch)
    
    total_mb = sum(len(b) for b in batches) / (1024 * 1024)
    print(f"Created {len(batches)} batches, {total_mb:.1f} MB total")
    
    return batches, num_frames


def main():
    parser = argparse.ArgumentParser(description="Ultra-fast fake camera for 10K+ FPS")
    parser.add_argument("--target", type=str, default="127.0.0.1", help="Converter IP")
    parser.add_argument("--port", type=int, default=6000, help="Converter port")
    parser.add_argument("--fps", type=int, default=10000, help="Target FPS (default: 10000)")
    parser.add_argument("--pregenerate", type=int, default=200, help="Frames to pre-generate")
    parser.add_argument("--batch", type=int, default=50, help="Frames per batch send (default: 50)")
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

    # Pre-generate frames in batches
    batches, num_frames = pregenerate_batch(args.pregenerate, args.batch)
    batch_frames = args.batch  # Frames per batch
    
    print(f"\n{'=' * 70}")
    print(f"Ultra-Fast Fake Camera (2-bit FPGA format)")
    print(f"{'=' * 70}")
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"Frame size: {FRAME_SIZE:,} bytes ({FRAME_SIZE/1024:.1f} KB)")
    print(f"Batch size: {batch_frames} frames ({batch_frames * FRAME_SIZE / 1024:.0f} KB per send)")
    print(f"Target: {args.target}:{args.port}")
    print(f"Mode: {'MAX SPEED' if args.no_ratelimit else f'{args.fps:,} FPS target'}")
    if target_bytes > 0:
        print(f"Goal: {args.target_gb} GB ({target_frames:,} frames)")
    if args.duration > 0:
        print(f"Duration: {args.duration} seconds")
    print(f"{'=' * 70}")
    
    # Throughput info
    if not args.no_ratelimit:
        throughput_mbps = (args.fps * FRAME_SIZE * 8) / 1_000_000
        throughput_gbps = throughput_mbps / 1000
        print(f"\nTarget throughput: {throughput_mbps:.0f} Mbps ({throughput_gbps:.1f} Gbps)")
        if throughput_gbps > 10:
            print(f"WARNING: {throughput_gbps:.1f} Gbps exceeds 10GbE capacity!")

    frame_interval = 1.0 / args.fps
    batch_interval = frame_interval * batch_frames

    while running:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        print(f"\nConnecting to {args.target}:{args.port}...")
        
        try:
            sock.connect((args.target, args.port))
            print("Connected!")
            
            # Maximize socket buffers
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

            print("\nSending frames (batch mode)...")
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

                # Get batch data
                batch_data = batches[batch_idx % len(batches)]
                frames_in_batch = len(batch_data) // FRAME_SIZE

                try:
                    # Send entire batch at once
                    sock.sendall(batch_data)
                    
                    batch_idx += 1
                    total_frames += frames_in_batch
                    total_bytes += len(batch_data)

                    # Progress report
                    now = time.time()
                    if now - last_report >= 0.5:  # Report every 0.5s for fast updates
                        elapsed = now - start_time
                        fps = total_frames / elapsed
                        gb_sent = total_bytes / BYTES_PER_GB
                        mbps = (total_bytes * 8) / (elapsed * 1_000_000)
                        gbps = mbps / 1000
                        
                        progress = ""
                        if target_bytes > 0:
                            pct = (total_bytes / target_bytes) * 100
                            eta = (target_bytes - total_bytes) / (total_bytes / elapsed) if total_bytes > 0 else 0
                            progress = f" | {pct:.1f}% (ETA: {eta:.0f}s)"
                        
                        print(f"Frames: {total_frames:>10,} | FPS: {fps:>8,.0f} | "
                              f"Sent: {gb_sent:>6.3f} GB | {gbps:>5.2f} Gbps{progress}")
                        
                        last_report = now

                    # Rate limiting (batch-based)
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
                print(f"FINAL RESULTS")
                print(f"{'=' * 70}")
                print(f"Total frames sent:  {total_frames:,}")
                print(f"Total data sent:    {gb_sent:.3f} GB ({total_bytes:,} bytes)")
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
                import traceback
                traceback.print_exc()
                print("Retrying in 2 seconds...")
                time.sleep(2)

    print("\nFast camera shutdown complete")


if __name__ == "__main__":
    main()
