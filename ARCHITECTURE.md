# TCP to AEDAT4 Converter - Architecture Document

## 1. Project Goal

Convert raw binary event camera frames received over TCP into AEDAT4 format,
and serve them via TCP so existing DV software can display them.

## 2. Known Information 

| Item | Value | Status |
|------|-------|--------|
| Frame dimensions | 1280 × 780 pixels|
| Channels | 2 (positive, negative) |
| Data format | Bits (1 bit per pixel per channel) | 
| Total frame size | 2 Mb = 249,600 bytes |
| Timestamps | NOT sent (frames only)|
| Protocol | TCP (most probably) |
| Frame rate | 500-1000 FPS |
| Connection type | Point-to-point |
| OS | Windows or Linux | 

## 3. Unknown Information (make configurable)

| Item | Default | Notes |
|------|---------|-------|
| TCP port | 5000 | Vedant will confirm |
| Frame header | Yes (4 bytes) | Unknown if camera sends size header |
| Bit order | LSB first | Unknown, may need to flip |
| Channel order | Positive first | Unknown which comes first |
| Pixel order | Row-major | Unknown, may be column-major |
| Byte order | Little-endian | Unknown |

**Strategy**: Make ALL unknowns configurable. If display looks wrong, flip a flag.

## 4. Data Flow

```
┌─────────────────┐     ┌─────────────────────────┐     ┌─────────────────┐
│  Event Camera   │────▶│   THIS CONVERTER        │────▶│   DV Viewer     │
│  (or simulator) │     │                         │     │   (existing)    │
│                 │     │  1. Receive TCP         │     │                 │
│  Sends binary   │     │  2. Unpack bits→events  │     │  Connects to    │
│  frames         │     │  3. Generate timestamps │     │  AEDAT4 stream  │
│                 │     │  4. Serve as AEDAT4     │     │                 │
│  Port: ?????    │     │  In: conf, Out: conf    │     │  Port: conf     │
└─────────────────┘     └─────────────────────────┘     └─────────────────┘
                              ALL CONFIGURABLE
```

## 5. Input Format (From Camera)

- **Protocol**: TCP (configurable: could support UDP later)
- **Frame dimensions**: 1280 x 780 pixels (configurable)
- **Channels**: 2 (positive events, negative events)
- **Encoding**: 1 bit per pixel per channel
- **Frame size**: 2 × 1280 × 780 / 8 = 249,600 bytes (auto-calculated)
- **Frame rate**: 500-1000 FPS
- **Timestamps**: NOT included - we generate them from frame rate
- **Header**: CONFIGURABLE (with or without size header)

### Frame Layout (configurable order):
```
[Optional N-byte header: frame size] ← configurable: has_header, header_size
[Channel A: 124,800 bytes]           ← configurable: positive_first
[Channel B: 124,800 bytes]
```

### Bit Layout (all configurable):
- Bit order: LSB first or MSB first ← configurable: msb_first
- Pixel order: Row-major or column-major ← configurable: row_major
- Channel order: Positive first or negative first ← configurable: positive_first

## 6. Output Format (To DV Viewer)

- **Protocol**: TCP (server mode)
- **Port**: CONFIGURABLE (default 7777)
- **Format**: AEDAT4 (handled by dv-processing library)
- **Data type**: Event stream (x, y, timestamp, polarity)
- **Timestamps**: Generated from frame number × frame_interval_us
- **Library**: dv::io::NetworkWriter

## 7. Module Breakdown

### 7.1 Config (include/config.hpp)
All adjustable parameters in one place:
- Frame: width, height
- Network: camera_ip, camera_port, aedat_port
- Bit unpacking: msb_first, positive_first, row_major
- Frame header: has_header, header_size
- Timing: frame_interval_us (for timestamp generation)

### 7.2 TCP Receiver (include/tcp_receiver.hpp, src/tcp_receiver.cpp)
- Connect to camera TCP server (IP and port configurable)
- Receive complete frames (handle partial reads)
- Support optional frame headers
- Cross-platform (Linux/Windows)
- Large receive buffer for high throughput

### 7.3 Frame Unpacker (include/frame_unpacker.hpp, src/frame_unpacker.cpp)
- Unpack binary bits into event list
- Convert to dv::EventStore format
- All bit/pixel ordering configurable
- Generate timestamps from frame count

### 7.4 Main (src/main.cpp)
- Load configuration
- Initialize components
- Main loop: receive → unpack → send
- Statistics printing (FPS, events/sec, throughput)
- Graceful shutdown

### 7.5 Test Simulator (test/fake_camera.py)
- Python script that simulates camera
- Generates moving patterns (circle, lines, etc.)
- Configurable: resolution, FPS, port
- For testing without real hardware

## 8. Dependencies

- **dv-processing**: AEDAT4 encoding and NetworkWriter
- **OpenCV**: Used by dv-processing internally
- **Standard sockets**: TCP networking (cross-platform)

## 9. Build & Run

```bash
# Build
mkdir build && cd build
cmake ..
make

# Terminal 1: Run fake camera (for testing)
python3 test/fake_camera.py

# Terminal 2: Run converter
./converter

# Terminal 3: View with DV software
dv-gui  # Then connect to 127.0.0.1:7777
# Or use command line:
dv-tcpstat -i 127.0.0.1 -p 7777 -r
```

## 10. Configuration Options

All options in `include/config.hpp`:

### Frame Settings
| Option | Default | Description |
|--------|---------|-------------|
| width | 1280 | Frame width in pixels |
| height | 780 | Frame height in pixels |

### Network Settings
| Option | Default | Description |
|--------|---------|-------------|
| camera_ip | "127.0.0.1" | Camera TCP server IP |
| camera_port | 5000 | Camera TCP server port |
| aedat_port | 7777 | AEDAT4 output server port |
| recv_buffer_size | 50MB | TCP receive buffer size |

### Bit Unpacking Settings (flip these if image looks wrong)
| Option | Default | Description |
|--------|---------|-------------|
| msb_first | false | Bit order: false=LSB first, true=MSB first |
| positive_first | true | Channel order: true=[pos][neg], false=[neg][pos] |
| row_major | true | Pixel order: true=row-by-row, false=column-by-column |

### Frame Header Settings
| Option | Default | Description |
|--------|---------|-------------|
| has_header | true | Does each frame have a size header? |
| header_size | 4 | Header size in bytes (if has_header=true) |

### Timing Settings
| Option | Default | Description |
|--------|---------|-------------|
| frame_interval_us | 2000 | Microseconds between frames (2000 = 500 FPS) |

## 11. Troubleshooting Guide

### If image looks flipped horizontally:
→ Try: `row_major = false`

### If image looks flipped vertically:
→ Try: swap positive_first

### If polarity seems inverted:
→ Try: `positive_first = false`

### If image looks like random noise:
→ Try: `msb_first = true`

### If receiving incomplete frames:
→ Check: `has_header` setting matches camera
→ Check: frame size calculation matches

## 12. File Structure

```
tcp-to-aedat4-converter/
├── ARCHITECTURE.md       # This document
├── README.md             # User instructions
├── CMakeLists.txt        # Build configuration
├── include/
│   ├── config.hpp        # ALL configuration options
│   ├── tcp_receiver.hpp  # TCP receiver class
│   └── frame_unpacker.hpp # Bit unpacking class
├── src/
│   ├── main.cpp          # Entry point
│   ├── tcp_receiver.cpp  # TCP implementation
│   └── frame_unpacker.cpp # Unpacker implementation
└── test/
    └── fake_camera.py    # Test camera simulator
```

## 13. Future Extensions (if needed)

- [ ] UDP support (for lower latency)
- [ ] Command-line argument parsing (override config)
- [ ] GUI controls (connect/disconnect buttons)
- [ ] Recording to file
- [ ] Multiple camera support
