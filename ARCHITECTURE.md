# DVBridge - Architecture Document

## 1. Project Goal

Convert raw binary event camera frames received over TCP into AEDAT4 format,
and serve them via TCP so existing DV software can display them.

## 2. FPGA Data Format

The FPGA sends frames using a 2-bit packed pixel format:

| Item | Value |
|------|-------|
| Frame dimensions | 1280 × 720 pixels |
| Pixels per frame | 921,600 |
| Bits per pixel | 2 |
| Bytes per frame | 230,400 |
| Pixel encoding | 00=none, 01=positive, 10=negative |
| Byte order | MSB first (pixel 0 in bits 7-6) |
| Protocol | TCP |
| Port | 6000 |
| Header | None (raw frames) |
| Frame rate | ~100 FPS (SLICE_PERIOD_US = 10000) |

### Pixel Encoding

```
Each pixel = 2 bits:
  00 = no event
  01 = positive polarity (p=1, brightness increased)
  10 = negative polarity (p=0, brightness decreased)
  11 = unused

Each byte contains 4 pixels (MSB first):
  Byte: [pixel0][pixel1][pixel2][pixel3]
        bits7-6 bits5-4 bits3-2 bits1-0
```

### FPGA set_pixel Reference

```cpp
static inline void set_pixel(uint8_t *frame, int x, int y, int p) {
    const size_t pixel_index = (size_t)y * W + (size_t)x;
    const size_t byte_index  = pixel_index >> 2;
    const int    shift       = (3 - (pixel_index & 3)) * 2;
    const uint8_t v = (p == 0) ? 0b10 : 0b01;
    frame[byte_index] = (frame[byte_index] & ~(0b11 << shift)) | (v << shift);
}
```

## 3. Data Flow

```
┌─────────────────┐     ┌─────────────────────────┐     ┌─────────────────┐
│  Event Camera   │────▶│   THIS CONVERTER        │────▶│   DV Viewer     │
│  (FPGA/ZCU)     │     │                         │     │   (existing)    │
│                 │     │  1. Receive TCP         │     │                 │
│  Sends 2-bit    │     │  2. Unpack 2-bit→events │     │  Connects to    │
│  packed frames  │     │  3. Generate timestamps │     │  AEDAT4 stream  │
│                 │     │  4. Serve as AEDAT4     │     │                 │
│  Port: 6000     │     │  Out: 7777              │     │  Port: 7777     │
└─────────────────┘     └─────────────────────────┘     └─────────────────┘
```

## 4. Output Format (To DV Viewer)

- **Protocol**: TCP (server mode)
- **Port**: 7777 (configurable)
- **Format**: AEDAT4 (handled by dv-processing library)
- **Data type**: Event stream (x, y, timestamp, polarity)
- **Timestamps**: Generated from frame number × frame_interval_us
- **Library**: dv::io::NetworkWriter

## 5. Module Breakdown

### 5.1 Config (include/config.hpp)
All adjustable parameters in one place:
- Frame: width, height
- Network: camera_ip, camera_port, aedat_port
- Frame header: has_header, header_size
- Timing: frame_interval_us (for timestamp generation)

### 5.2 TCP Receiver (include/tcp_receiver.hpp, src/tcp_receiver.cpp)
- Connect to camera TCP server (IP and port configurable)
- Receive complete frames (handle partial reads)
- Support optional frame headers
- Cross-platform (Linux/Windows)
- Large receive buffer for high throughput

### 5.3 UDP Receiver (include/udp_receiver.hpp, src/udp_receiver.cpp)
- Bind to UDP port and receive datagrams
- Accumulate packets into complete frames
- Handle leftover bytes across frame boundaries

### 5.4 Frame Unpacker (include/frame_unpacker.hpp, src/frame_unpacker.cpp)
- Unpack 2-bit packed pixels into event list
- Convert to dv::EventStore format
- Generate timestamps from frame count
- Optimized for sparse data (skip zero bytes)

### 5.5 Main (src/main.cpp)
- Load configuration
- Initialize components
- Main loop: receive → unpack → send
- Statistics printing (FPS, events/sec, throughput)
- Graceful shutdown

### 5.6 Test Simulator (test/fake_camera.py)
- Python script that simulates FPGA
- Generates moving patterns using 2-bit encoding
- Matches FPGA frame format exactly
- Configurable: resolution, FPS, port

## 6. Dependencies

- **dv-processing**: AEDAT4 encoding and NetworkWriter
- **OpenCV**: Used by dv-processing internally
- **Standard sockets**: TCP/UDP networking (cross-platform)

## 7. Build & Run

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
```

## 8. Configuration Options

All options in `include/config.hpp`:

### Frame Settings
| Option | Default | Description |
|--------|---------|-------------|
| width | 1280 | Frame width in pixels |
| height | 720 | Frame height in pixels |

### Network Settings
| Option | Default | Description |
|--------|---------|-------------|
| camera_ip | "0.0.0.0" | Bind address (TCP: unused, UDP: bind to all interfaces) |
| camera_port | 6000 | Port to listen on (FPGA connects here) |
| aedat_port | 7777 | AEDAT4 output server port |
| recv_buffer_size | 50MB | TCP receive buffer size |

### Frame Header Settings
| Option | Default | Description |
|--------|---------|-------------|
| has_header | false | Does each frame have a size header? |
| header_size | 4 | Header size in bytes (if has_header=true) |

### Timing Settings
| Option | Default | Description |
|--------|---------|-------------|
| frame_interval_us | 10000 | Microseconds between frames (10000 = 100 FPS) |

## 9. Frame Unpacking Algorithm

```cpp
// For each byte in the frame:
for (int byte_idx = 0; byte_idx < frame_size; byte_idx++) {
    uint8_t byte_val = frame_data[byte_idx];
    
    // Skip zero bytes (no events)
    if (byte_val == 0) continue;
    
    // Extract 4 pixels from this byte
    for (int px = 0; px < 4; px++) {
        int shift = 6 - (px * 2);  // 6, 4, 2, 0
        uint8_t pixel_val = (byte_val >> shift) & 0x03;
        
        if (pixel_val == 1 || pixel_val == 2) {
            int pixel_idx = byte_idx * 4 + px;
            int x = pixel_idx % width;
            int y = pixel_idx / width;
            bool polarity = (pixel_val == 1);  // 01=positive, 10=negative
            
            events.emplace_back(timestamp, x, y, polarity);
        }
    }
}
```

## 10. File Structure

```
DVBridge/
├── ARCHITECTURE.md          # This document
├── README.md                # User instructions
├── CMakeLists.txt           # Build configuration
├── include/
│   ├── config.hpp           # ALL configuration options
│   ├── tcp_receiver.hpp     # TCP receiver class
│   ├── udp_receiver.hpp     # UDP receiver class
│   └── frame_unpacker.hpp   # 2-bit unpacking class
├── src/
│   ├── main.cpp             # Entry point
│   ├── tcp_receiver.cpp     # TCP implementation
│   ├── udp_receiver.cpp     # UDP implementation
│   └── frame_unpacker.cpp   # Unpacker implementation
└── test/
    ├── fake_camera.py       # Basic TCP simulator (moving circles)
    ├── fake_camera_udp.py   # UDP simulator
    ├── fast_fake_camera.py  # High-speed TCP test (10K+ FPS)
    └── realistic_camera.py  # Realistic event patterns
```

## 11. Future Extensions (if needed)

- [ ] Command-line argument parsing (override config)
- [ ] GUI controls (connect/disconnect buttons)
- [ ] Recording to file
- [ ] Multiple camera support
- [ ] Variable frame size support
