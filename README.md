# TCP to AEDAT4 Converter

Convert raw binary event camera frames received over TCP into AEDAT4 format for display in DV software.

## Overview

```text
FPGA/Camera  ──TCP──►  [Converter]  ──TCP──►  DV Viewer (visualization)
 (client)         (server:6000)          (server:7777)
```

This software acts as a bridge between custom event camera hardware and the DV ecosystem:
1. Acts as TCP server - FPGA connects to converter on port 6000
2. Receives binary 2-bit packed frames
3. Converts frames to AEDAT4 event format
4. Streams events to DV viewer (which connects on port 7777)

---

## Frame Format (FPGA 2-bit Packed)

The converter expects the FPGA's 2-bit packed pixel format:

```text
Each pixel = 2 bits:
  00 = no event
  01 = positive polarity (brightness increased)
  10 = negative polarity (brightness decreased)
  11 = unused

4 pixels per byte, MSB first:
  Byte: [pixel0:2][pixel1:2][pixel2:2][pixel3:2]
        bits 7-6   bits 5-4   bits 3-2   bits 1-0

Frame size = (width × height + 3) / 4 bytes
For 1280×720: 230,400 bytes
```

---

## Installation

### Step 1: Install Dependencies (Ubuntu 20.04+)

```bash
# Update package list
sudo apt update

# Add iniVation repository
sudo add-apt-repository ppa:inivation-ppa/inivation
sudo apt update

# Install required packages
sudo apt install -y build-essential cmake git python3
sudo apt install -y dv-processing dv-gui
```

**Package descriptions:**
| Package | Purpose |
|---------|---------|
| `build-essential` | C++ compiler (GCC) |
| `cmake` | Build system |
| `dv-processing` | AEDAT4 encoding library |
| `dv-gui` | Event visualization software |

### Step 2: Build the Converter

```bash
# Clone repository
cd ~
git clone https://github.com/berkyilmaz01/tcp-to-aedat4-converter.git
cd tcp-to-aedat4-converter

# Build
mkdir build && cd build
cmake ..
make
```

A successful build produces the `converter` executable in the build directory.

### Step 3: Configure Settings

Edit the configuration file to match the hardware specifications:
```bash
nano ~/tcp-to-aedat4-converter/include/config.hpp
```

**Required settings:**

| Setting | Description | Default |
|---------|-------------|---------|
| `width` | Frame width in pixels | 1280 |
| `height` | Frame height in pixels | 720 |
| `camera_ip` | FPGA/camera IP address | 127.0.0.1 |
| `camera_port` | TCP port for incoming frames | 6000 |
| `has_header` | Whether frames include size header | false |
| `frame_interval_us` | Microseconds between frames | 10000 (100 FPS) |

After modifying settings, rebuild:
```bash
cd ~/tcp-to-aedat4-converter/build
make
```

---

## Testing with Simulator

Before connecting hardware, verify the setup using the included camera simulator.

### Test Procedure (Requires 3 Terminals)

**Terminal 1 - Start Camera Simulator:**
```bash
cd ~/tcp-to-aedat4-converter
python3 test/fake_camera.py
```
Expected output:
```text
==================================================
Fake Camera Simulator (2-bit FPGA format)
==================================================
Resolution: 1280x720
Frame size: 230400 bytes (2-bit packed)
TCP port: 6000
Target FPS: 100
Header: disabled (raw frames)
==================================================
Waiting for connection...
```

**Terminal 2 - Start Converter:**
```bash
cd ~/tcp-to-aedat4-converter/build
./converter
```
Expected output:
```text
TCP/UDP to AEDAT4 Converter
Configuration:
  Frame size: 1280 x 720
  Frame data size: 230400 bytes
  ...
Connecting to camera...
Connected successfully!
```

**Terminal 3 - Start DV Viewer:**
```bash
dv-gui
```

### DV Viewer Configuration

1. Click **"Add Module"** (top left)
2. Select **"Input"** → **"Network TCP Client"**
3. Configure module settings:
   - **IP Address**: `127.0.0.1`
   - **Port**: `7777`
4. Click the **Play button** to start visualization
5. Two moving circles should appear (positive and negative polarity events)

```text
Expected visualization:
┌────────────────────────────┐
│     ●                      │  ← Positive events (horizontal motion)
│           ○                │  ← Negative events (vertical motion)
│                            │
└────────────────────────────┘
```

---

## Hardware Connection

### Network Configuration

**Option A: Direct Connection**
- Connect FPGA directly to PC via Ethernet cable
- Configure static IPs:
  - FPGA: 192.168.50.10
  - PC: 192.168.50.20

**Option B: Through Network Switch**
- Connect both devices to the same switch/router
- Use DHCP or configure static IPs on the same subnet

### Software Configuration

Update the configuration file with the FPGA network settings:
```bash
nano ~/tcp-to-aedat4-converter/include/config.hpp
```

```cpp
std::string camera_ip = "192.168.50.10";  // FPGA IP address
int camera_port = 6000;                    // FPGA TCP port
```

Rebuild after configuration changes:
```bash
cd ~/tcp-to-aedat4-converter/build
make
```

### Running with Hardware

**Terminal 1 - Start Converter:**
```bash
cd ~/tcp-to-aedat4-converter/build
./converter
```

**Terminal 2 - Start DV Viewer:**
```bash
dv-gui
# Connect to 127.0.0.1:7777 as described above
```

**FPGA Side:** Initiate frame transmission to the PC IP address on port 6000.

---

## FPGA Data Format Reference

### Frame Layout (2-bit packed pixels)
```text
┌─────────────────────────────────────────────────┐
│                 Frame Data                       │
│            230,400 bytes (for 1280×720)          │
│                                                  │
│  Each byte = 4 pixels:                           │
│  [p0:2][p1:2][p2:2][p3:2]                       │
│                                                  │
│  Pixel values:                                   │
│    00 = no event                                 │
│    01 = positive (brightness increased)          │
│    10 = negative (brightness decreased)          │
│    11 = unused                                   │
└─────────────────────────────────────────────────┘
```

### FPGA set_pixel Function (Reference)
```cpp
// From FPGA code - how pixels are encoded
static inline void set_pixel(uint8_t *frame, int x, int y, int p) {
    const size_t pixel_index = (size_t)y * W + (size_t)x;
    const size_t byte_index  = pixel_index >> 2;  // divide by 4
    const int    shift       = (3 - (pixel_index & 3)) * 2;
    const uint8_t v = (p == 0) ? 0b10 : 0b01;  // p=0 → 10, p=1 → 01
    frame[byte_index] = (frame[byte_index] & ~(0b11 << shift)) | (v << shift);
}
```

---

## Troubleshooting

### Connection Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Failed to connect to camera" | Incorrect IP/port or network issue | Verify IP address in config; test with `ping` |
| "Connection closed by server" | FPGA stopped transmitting | Verify FPGA is running and sending data |
| No events in DV viewer | DV connected to wrong port | Connect DV to port 7777 (not 6000) |

### Image Quality Issues

| Symptom | Solution |
|---------|----------|
| Random noise pattern | Verify frame size matches (230,400 bytes for 1280×720) |
| No events showing | Check that FPGA is encoding pixels correctly |
| Partial image | Verify `width` and `height` match sensor resolution |
| Wrong coordinates | Check row-major ordering matches FPGA |

### Performance Issues

| Symptom | Solution |
|---------|----------|
| Low frame rate | Use wired Ethernet (not WiFi) |
| Dropped frames | Increase `recv_buffer_size` (default: 50MB) |
| High latency | Use direct Ethernet connection |

---

## Quick Reference

### Commands

```bash
# Build
cd ~/tcp-to-aedat4-converter/build && make

# Run converter
./converter

# Run simulator (TCP)
python3 ~/tcp-to-aedat4-converter/test/fake_camera.py

# Run simulator with options
python3 test/fake_camera.py --port 6000 --fps 100

# Launch DV viewer
dv-gui
```

### Network Ports

| Port | Function | Direction |
|------|----------|-----------|
| 6000 | Frame input | Camera/FPGA → Converter |
| 7777 | Event output | Converter → DV Viewer |

### File Locations

| File | Description |
|------|-------------|
| `include/config.hpp` | Configuration settings |
| `build/converter` | Main executable |
| `test/fake_camera.py` | Camera simulator (TCP) |
| `test/fake_camera_udp.py` | Camera simulator (UDP) |

---

## Technical Specifications

| Parameter | Value |
|-----------|-------|
| Resolution | 1280 × 720 pixels |
| Pixels per frame | 921,600 |
| Frame size | 230,400 bytes |
| Pixel encoding | 2-bit packed (4 pixels/byte) |
| Target frame rate | 100 FPS (configurable) |
| Frame interval | 10,000 μs |
| Protocol | TCP/IP |
| Output format | AEDAT4 |

---

## Additional Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical design documentation
- Contact: Berk Yilmaz

## License

MIT License
