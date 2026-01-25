#!/usr/bin/env python3
"""
Fake Camera Simulator for TCP-to-AEDAT4 Converter Testing

Generates binary frames with a moving circle pattern and sends via TCP.
This simulates the FPGA/chip output that the converter expects.

Usage:
    python3 fake_camera.py [--port 5000] [--fps 500] [--no-header]
"""

import socket
import struct
import time
import argparse
import signal
import sys
import math

# Frame configuration (must match config.hpp)
WIDTH = 1280
HEIGHT = 780
CHANNELS = 2  # positive and negative
BYTES_PER_CHANNEL = (WIDTH * HEIGHT) // 8  # 124,800 bytes
FRAME_SIZE = CHANNELS * BYTES_PER_CHANNEL   # 249,600 bytes

# Running flag for graceful shutdown
running = True

def signal_handler(sig, frame):
    global running
    print("\nShutting down...")
    running = False

def create_circle_frame(cx: int, cy: int, radius: int, positive: bool = True) -> bytes:
    """
    Create a binary frame with a filled circle.
    Returns bytes for one channel (positive or negative).
    """
    # Create bit array (row-major, LSB first to match default config)
    data = bytearray(BYTES_PER_CHANNEL)
    
    for y in range(HEIGHT):
        for x in range(WIDTH):
            # Check if pixel is inside circle
            dx = x - cx
            dy = y - cy
            if dx*dx + dy*dy <= radius*radius:
                # Set this bit
                bit_index = y * WIDTH + x
                byte_index = bit_index // 8
                bit_offset = bit_index % 8  # LSB first
                data[byte_index] |= (1 << bit_offset)
    
    return bytes(data)

def create_moving_pattern_frame(frame_num: int) -> bytes:
    """
    Create a frame with a moving circle pattern.
    Positive channel: circle moving right
    Negative channel: circle moving left
    """
    # Circle parameters
    radius = 50
    
    # Positive circle: moves horizontally
    period_x = 200  # frames for one cycle
    cx_pos = int(WIDTH/2 + (WIDTH/3) * math.sin(2 * math.pi * frame_num / period_x))
    cy_pos = HEIGHT // 2
    
    # Negative circle: moves vertically, offset position
    period_y = 150
    cx_neg = WIDTH // 2
    cy_neg = int(HEIGHT/2 + (HEIGHT/3) * math.sin(2 * math.pi * frame_num / period_y))
    
    # Create both channels
    pos_data = create_circle_frame(cx_pos, cy_pos, radius, positive=True)
    neg_data = create_circle_frame(cx_neg, cy_neg, radius, positive=False)
