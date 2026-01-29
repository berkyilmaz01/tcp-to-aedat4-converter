#!/usr/bin/env python3
"""
Realistic Event Camera Simulator

Generates high-quality, realistic event camera data at 10K+ FPS.
Pre-generates frames using numpy for maximum performance.

Features:
- Realistic edge-based event patterns
- Moving objects with proper event generation
- Background noise similar to real DVS sensors
- Text rendering with event-like appearance
- Multiple scene modes

Usage:
    python3 realistic_camera.py
    python3 realistic_camera.py --scene objects --fps 10000
    python3 realistic_camera.py --scene text --text "IAI" --fps 5000
"""

import socket
import numpy as np
import cv2
import signal
import sys
import time
import argparse
from dataclasses import dataclass

# Settings
WIDTH = 1280
HEIGHT = 720
FRAME_SIZE = (WIDTH * HEIGHT + 3) // 4
PORT = 6000

running = True

def signal_handler(sig, frame):
    global running
    print("\n[INFO] Shutting down...")
    running = False

signal.signal(signal.SIGINT, signal_handler)


@dataclass
class MovingObject:
    """A moving object that generates events at its edges"""
    x: float
    y: float
    vx: float
    vy: float
    width: int
    height: int
    shape: str = "circle"  # "circle", "rectangle", "triangle"


class RealisticEventGenerator:
    """
    Generates realistic event camera frames.
    
    Event cameras detect brightness changes, so events appear at:
    - Edges of moving objects
    - Texture boundaries
    - Flickering lights
    
    This simulator creates realistic patterns by:
    1. Tracking object positions
    2. Generating events at edges when objects move
    3. Adding realistic sensor noise
    """
    
    def __init__(self, width, height, noise_level=0.0005, edge_thickness=2):
        self.width = width
        self.height = height
        self.noise_level = noise_level
        self.edge_thickness = edge_thickness
        
        # Previous frame for edge detection
        self.prev_frame = np.zeros((height, width), dtype=np.uint8)
        
        # Objects in scene
        self.objects = []
        
        # Pre-computed noise patterns (for speed)
        self.noise_patterns = []
        self._precompute_noise(100)
        
    def _precompute_noise(self, count):
        """Pre-compute noise patterns for speed"""
        print(f"[INFO] Pre-computing {count} noise patterns...")
        for _ in range(count):
            noise = np.random.random((self.height, self.width)) < self.noise_level
            # Random polarity for noise
            polarity = np.random.randint(0, 2, (self.height, self.width))
            self.noise_patterns.append((noise, polarity))
    
    def add_object(self, obj: MovingObject):
        """Add a moving object to the scene"""
        self.objects.append(obj)
    
    def create_random_objects(self, count=5):
        """Create random moving objects"""
        for _ in range(count):
            obj = MovingObject(
                x=np.random.uniform(100, self.width - 100),
                y=np.random.uniform(100, self.height - 100),
                vx=np.random.uniform(-5, 5),
                vy=np.random.uniform(-5, 5),
                width=np.random.randint(30, 100),
                height=np.random.randint(30, 100),
                shape=np.random.choice(["circle", "rectangle"])
            )
            self.objects.append(obj)
    
    def _draw_object(self, frame, obj):
        """Draw an object on the frame"""
        x, y = int(obj.x), int(obj.y)
        
        if obj.shape == "circle":
            radius = obj.width // 2
            cv2.circle(frame, (x, y), radius, 255, -1)
        elif obj.shape == "rectangle":
            cv2.rectangle(frame, 
                         (x - obj.width//2, y - obj.height//2),
                         (x + obj.width//2, y + obj.height//2),
                         255, -1)
        elif obj.shape == "triangle":
            pts = np.array([
                [x, y - obj.height//2],
                [x - obj.width//2, y + obj.height//2],
                [x + obj.width//2, y + obj.height//2]
            ], np.int32)
            cv2.fillPoly(frame, [pts], 255)
    
    def _update_objects(self):
        """Update object positions with bouncing"""
        for obj in self.objects:
            obj.x += obj.vx
            obj.y += obj.vy
            
            # Bounce off walls
            if obj.x < obj.width//2 or obj.x > self.width - obj.width//2:
                obj.vx *= -1
                obj.x = np.clip(obj.x, obj.width//2, self.width - obj.width//2)
            if obj.y < obj.height//2 or obj.y > self.height - obj.height//2:
                obj.vy *= -1
                obj.y = np.clip(obj.y, obj.height//2, self.height - obj.height//2)
    
    def generate_frame_objects(self, frame_idx):
        """Generate a frame with moving objects (edge events)"""
        # Create current frame with objects
        current_frame = np.zeros((self.height, self.width), dtype=np.uint8)
        
        for obj in self.objects:
            self._draw_object(current_frame, obj)
        
        # Detect edges using difference
        diff = cv2.absdiff(current_frame, self.prev_frame)
        
        # Dilate edges slightly for visibility
        kernel = np.ones((self.edge_thickness, self.edge_thickness), np.uint8)
        edges = cv2.dilate(diff, kernel, iterations=1)
        
        # Determine polarity based on brightness change
        # Positive (brighter) where current > prev
        # Negative (darker) where current < prev
        pos_events = (current_frame > self.prev_frame) & (edges > 0)
        neg_events = (current_frame < self.prev_frame) & (edges > 0)
        
        # Add noise
        noise, noise_pol = self.noise_patterns[frame_idx % len(self.noise_patterns)]
        pos_events = pos_events | (noise & (noise_pol == 1))
        neg_events = neg_events | (noise & (noise_pol == 0))
        
        # Update state
        self.prev_frame = current_frame.copy()
        self._update_objects()
        
        return pos_events, neg_events
    
    def render_text_with_events(self, text, x, y, font_scale=4, thickness=8):
        """Render text as event-like dots/edges"""
        # Create text mask
        mask = np.zeros((self.height, self.width), dtype=np.uint8)
        
        # Get text size for centering
        font = cv2.FONT_HERSHEY_SIMPLEX
        (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        
        # Center if x,y are -1
        if x < 0:
            x = (self.width - text_width) // 2
        if y < 0:
            y = (self.height + text_height) // 2
        
        # Draw text
        cv2.putText(mask, text, (x, y), font, font_scale, 255, thickness)
        
        # Get edge pixels (outline of text)
        edges = cv2.Canny(mask, 50, 150)
        
        # Dilate for visibility
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)
        
        return edges > 0


class SceneGenerator:
    """Generates different scene types"""
    
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.event_gen = RealisticEventGenerator(width, height)
        
    def pregenerate_objects_scene(self, num_frames, num_objects=5):
        """Pre-generate frames with bouncing objects"""
        print(f"[INFO] Pre-generating {num_frames} frames with {num_objects} objects...")
        
        self.event_gen.create_random_objects(num_objects)
        
        frames = []
        for i in range(num_frames):
            pos, neg = self.event_gen.generate_frame_objects(i)
            frame = self._pack_frame(pos, neg)
            frames.append(frame)
            
            if (i + 1) % 1000 == 0:
                print(f"  Generated {i+1}/{num_frames} frames")
        
        return frames
    
    def pregenerate_text_scene(self, text, num_frames, animation="scroll"):
        """Pre-generate frames with animated text"""
        print(f"[INFO] Pre-generating {num_frames} frames with text '{text}'...")
        
        frames = []
        
        # Get text dimensions
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 6
        thickness = 12
        (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
        
        for i in range(num_frames):
            # Create frame
            pos_events = np.zeros((self.height, self.width), dtype=bool)
            neg_events = np.zeros((self.height, self.width), dtype=bool)
            
            if animation == "scroll":
                # Scroll text from right to left
                x = self.width - (i * 3) % (self.width + text_width)
                y = self.height // 2 + text_height // 2
            elif animation == "pulse":
                # Pulsing text (scale varies)
                scale = font_scale + np.sin(i * 0.1) * 1.5
                x = -1  # Center
                y = -1
            elif animation == "wave":
                # Wavy text
                x = (self.width - text_width) // 2
                y = self.height // 2 + int(np.sin(i * 0.1) * 50)
            else:  # static
                x = -1
                y = -1
            
            # Render text edges
            text_events = self._render_text_edges(text, x, y, font_scale, thickness)
            
            # Alternate polarity for visual effect (creates flickering outline)
            if i % 2 == 0:
                pos_events = text_events
            else:
                neg_events = text_events
            
            # Add some noise
            noise_level = 0.0002
            noise = np.random.random((self.height, self.width)) < noise_level
            noise_pol = np.random.randint(0, 2, (self.height, self.width))
            pos_events = pos_events | (noise & (noise_pol == 1))
            neg_events = neg_events | (noise & (noise_pol == 0))
            
            frame = self._pack_frame(pos_events, neg_events)
            frames.append(frame)
            
            if (i + 1) % 1000 == 0:
                print(f"  Generated {i+1}/{num_frames} frames")
        
        return frames
    
    def pregenerate_dots_text(self, text, num_frames):
        """Pre-generate text made of event dots (realistic DVS look)"""
        print(f"[INFO] Pre-generating {num_frames} frames with dotted text '{text}'...")
        
        # Create base text mask
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 8
        thickness = 15
        
        mask = np.zeros((self.height, self.width), dtype=np.uint8)
        (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
        x = (self.width - text_width) // 2
        y = (self.height + text_height) // 2
        cv2.putText(mask, text, (x, y), font, font_scale, 255, thickness)
        
        # Get text pixels
        text_pixels = np.where(mask > 0)
        num_text_pixels = len(text_pixels[0])
        
        print(f"  Text has {num_text_pixels} pixels")
        
        frames = []
        
        for i in range(num_frames):
            pos_events = np.zeros((self.height, self.width), dtype=bool)
            neg_events = np.zeros((self.height, self.width), dtype=bool)
            
            # Randomly select subset of text pixels to "fire" as events
            # This creates a realistic flickering/dotted appearance
            fire_prob = 0.3 + 0.2 * np.sin(i * 0.05)  # Vary density
            fire_mask = np.random.random(num_text_pixels) < fire_prob
            
            # Get firing pixels
            fire_y = text_pixels[0][fire_mask]
            fire_x = text_pixels[1][fire_mask]
            
            # Assign random polarities (creates texture)
            polarities = np.random.randint(0, 2, len(fire_y))
            
            pos_events[fire_y[polarities == 1], fire_x[polarities == 1]] = True
            neg_events[fire_y[polarities == 0], fire_x[polarities == 0]] = True
            
            # Add edge emphasis (edges fire more often)
            edges = cv2.Canny(mask, 50, 150)
            edge_pixels = np.where(edges > 0)
            if len(edge_pixels[0]) > 0:
                edge_fire = np.random.random(len(edge_pixels[0])) < 0.5
                edge_y = edge_pixels[0][edge_fire]
                edge_x = edge_pixels[1][edge_fire]
                edge_pol = np.random.randint(0, 2, len(edge_y))
                pos_events[edge_y[edge_pol == 1], edge_x[edge_pol == 1]] = True
                neg_events[edge_y[edge_pol == 0], edge_x[edge_pol == 0]] = True
            
            # Add background noise
            noise_level = 0.0003
            noise = np.random.random((self.height, self.width)) < noise_level
            noise_pol = np.random.randint(0, 2, (self.height, self.width))
            pos_events = pos_events | (noise & (noise_pol == 1))
            neg_events = neg_events | (noise & (noise_pol == 0))
            
            frame = self._pack_frame(pos_events, neg_events)
            frames.append(frame)
            
            if (i + 1) % 1000 == 0:
                print(f"  Generated {i+1}/{num_frames} frames")
        
        return frames
    
    def pregenerate_mixed_scene(self, text, num_frames, num_objects=3):
        """Pre-generate scene with both text and moving objects"""
        print(f"[INFO] Pre-generating {num_frames} mixed scene frames...")
        
        # Setup objects
        self.event_gen.create_random_objects(num_objects)
        
        # Create static text mask
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 6
        thickness = 10
        
        text_mask = np.zeros((self.height, self.width), dtype=np.uint8)
        (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
        x = (self.width - text_width) // 2
        y = self.height // 4  # Upper part
        cv2.putText(text_mask, text, (x, y), font, font_scale, 255, thickness)
        
        text_pixels = np.where(text_mask > 0)
        num_text_pixels = len(text_pixels[0])
        
        frames = []
        
        for i in range(num_frames):
            # Get object events
            pos_obj, neg_obj = self.event_gen.generate_frame_objects(i)
            
            # Get text events (flickering)
            pos_text = np.zeros((self.height, self.width), dtype=bool)
            neg_text = np.zeros((self.height, self.width), dtype=bool)
            
            fire_prob = 0.25
            fire_mask = np.random.random(num_text_pixels) < fire_prob
            fire_y = text_pixels[0][fire_mask]
            fire_x = text_pixels[1][fire_mask]
            polarities = np.random.randint(0, 2, len(fire_y))
            
            pos_text[fire_y[polarities == 1], fire_x[polarities == 1]] = True
            neg_text[fire_y[polarities == 0], fire_x[polarities == 0]] = True
            
            # Combine
            pos_events = pos_obj | pos_text
            neg_events = neg_obj | neg_text
            
            frame = self._pack_frame(pos_events, neg_events)
            frames.append(frame)
            
            if (i + 1) % 1000 == 0:
                print(f"  Generated {i+1}/{num_frames} frames")
        
        return frames
    
    def _render_text_edges(self, text, x, y, font_scale, thickness):
        """Render text and return edge pixels"""
        mask = np.zeros((self.height, self.width), dtype=np.uint8)
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        if x < 0 or y < 0:
            (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
            if x < 0:
                x = (self.width - text_width) // 2
            if y < 0:
                y = (self.height + text_height) // 2
        
        cv2.putText(mask, text, (int(x), int(y)), font, font_scale, 255, thickness)
        edges = cv2.Canny(mask, 50, 150)
        kernel = np.ones((2, 2), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)
        
        return edges > 0
    
    def _pack_frame(self, pos_events, neg_events):
        """Pack events into 2-bit format"""
        # Create pixel array: 0=none, 1=positive, 2=negative
        pixels = np.zeros((self.height, self.width), dtype=np.uint8)
        pixels[pos_events] = 1
        pixels[neg_events] = 2
        
        # Flatten
        pixels_flat = pixels.flatten()
        
        # Pad to multiple of 4
        pad_len = (4 - len(pixels_flat) % 4) % 4
        if pad_len > 0:
            pixels_flat = np.concatenate([pixels_flat, np.zeros(pad_len, dtype=np.uint8)])
        
        # Reshape to groups of 4
        pixels_grouped = pixels_flat.reshape(-1, 4)
        
        # Pack: [p0, p1, p2, p3] -> byte with p0 in bits 7-6, p1 in 5-4, etc.
        packed = (
            (pixels_grouped[:, 0] << 6) |
            (pixels_grouped[:, 1] << 4) |
            (pixels_grouped[:, 2] << 2) |
            pixels_grouped[:, 3]
        ).astype(np.uint8)
        
        return packed.tobytes()


def main():
    global running
    
    parser = argparse.ArgumentParser(description="Realistic Event Camera Simulator")
    parser.add_argument("--scene", type=str, default="dots", 
                       choices=["objects", "text", "dots", "mixed"],
                       help="Scene type")
    parser.add_argument("--text", type=str, default="IAI", help="Text to display")
    parser.add_argument("--fps", type=int, default=10000, help="Target FPS")
    parser.add_argument("--frames", type=int, default=10000, help="Frames to pre-generate")
    parser.add_argument("--port", type=int, default=PORT, help="TCP port")
    parser.add_argument("--objects", type=int, default=5, help="Number of objects")
    args = parser.parse_args()
    
    print("=" * 60)
    print("   REALISTIC EVENT CAMERA SIMULATOR")
    print("=" * 60)
    print(f"   Scene: {args.scene}")
    print(f"   Text: '{args.text}'")
    print(f"   Target FPS: {args.fps}")
    print(f"   Pre-generating: {args.frames} frames")
    print(f"   Port: {args.port}")
    print("=" * 60)
    print()
    
    # Generate frames
    generator = SceneGenerator(WIDTH, HEIGHT)
    
    if args.scene == "objects":
        frames = generator.pregenerate_objects_scene(args.frames, args.objects)
    elif args.scene == "text":
        frames = generator.pregenerate_text_scene(args.text, args.frames, "scroll")
    elif args.scene == "dots":
        frames = generator.pregenerate_dots_text(args.text, args.frames)
    elif args.scene == "mixed":
        frames = generator.pregenerate_mixed_scene(args.text, args.frames, args.objects)
    
    print(f"\n[INFO] Generated {len(frames)} frames ({len(frames) * FRAME_SIZE / 1024 / 1024:.1f} MB)")
    print(f"[INFO] At {args.fps} FPS, this is {len(frames) / args.fps:.1f} seconds of data")
    print()
    
    # Connect to viewer
    print(f"[INFO] Connecting to viewer on port {args.port}...")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    
    try:
        sock.connect(("127.0.0.1", args.port))
        print("[INFO] Connected!")
    except Exception as e:
        print(f"[ERROR] Failed to connect: {e}")
        print("[INFO] Make sure the viewer (pro_viewer.py) is running first!")
        return
    
    # Send frames
    print(f"[INFO] Streaming at {args.fps} FPS...")
    print("[INFO] Press Ctrl+C to stop")
    print()
    
    frame_interval = 1.0 / args.fps
    frame_idx = 0
    start_time = time.time()
    sent_frames = 0
    last_report_time = start_time
    
    try:
        while running:
            loop_start = time.time()
            
            # Send frame
            frame = frames[frame_idx % len(frames)]
            sock.sendall(frame)
            
            sent_frames += 1
            frame_idx += 1
            
            # Report progress every second
            current_time = time.time()
            if current_time - last_report_time >= 1.0:
                elapsed = current_time - start_time
                actual_fps = sent_frames / elapsed
                print(f"[STATUS] Sent: {sent_frames:,} frames | FPS: {actual_fps:.0f} | "
                      f"Loop: {frame_idx % len(frames)}/{len(frames)}")
                last_report_time = current_time
            
            # Pace sending (if needed for lower FPS)
            if args.fps < 50000:
                elapsed = time.time() - loop_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
    except BrokenPipeError:
        print("\n[INFO] Viewer disconnected")
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user")
    finally:
        sock.close()
        
        # Final stats
        elapsed = time.time() - start_time
        print()
        print("=" * 60)
        print("   SESSION SUMMARY")
        print("=" * 60)
        print(f"   Frames sent: {sent_frames:,}")
        print(f"   Duration: {elapsed:.1f} seconds")
        print(f"   Average FPS: {sent_frames / elapsed:.0f}")
        print(f"   Data sent: {sent_frames * FRAME_SIZE / 1024 / 1024:.1f} MB")
        print("=" * 60)


if __name__ == "__main__":
    main()
