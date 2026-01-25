# TCP to AEDAT4 Converter

Convert raw binary event camera frames received over TCP into AEDAT4 format for display in DV software.

## Overview

```text
FPGA/Camera  ──TCP──►  [Converter]  ──TCP──►  DV Viewer (visualization)
 (port 5000)                                    (port 7777)
```

This software acts as a bridge between custom event camera hardware and the DV ecosystem:
1. Receives binary bit-packed frames over TCP
2. Converts frames to AEDAT4 event format
3. Streams events to DV viewer for real-time visualization

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
| `height` | Frame height in pixels | 780 |
| `camera_ip` | FPGA/camera IP address | 127.0.0.1 |
| `camera_port` | TCP port for incoming frames | 5000 |
| `has_header` | Whether frames include 4-byte size header | true |

**Bit unpacking settings (adjust if output appears incorrect):**

| Setting | Effect |
|---------|--------|
| `msb_first = true` | Use if output appears as random noise |
| `positive_first = false` | Use if polarity is inverted |
| `row_major = false` | Use if image is rotated 90 degrees |

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
Fake camera listening on port 5000
Frame size: 249600 bytes (1280x780, 2 channels)
Target FPS: 500
Waiting for connection...
```

**Terminal 2 - Start Converter:**
```bash
cd ~/tcp-to-aedat4-converter/build
./converter
```
Expected output:
```text
TCP to AEDAT4 Converter
Configuration:
  Frame size: 1280 x 780
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
  - FPGA: 192.168.1.100
  - PC: 192.168.1.1

**Option B: Through Network Switch**
- Connect both devices to the same switch/router
- Use DHCP or configure static IPs on the same subnet

### Software Configuration

Update the configuration file with the FPGA network settings:
```bash
nano ~/tcp-to-aedat4-converter/include/config.hpp
```

```cpp
std::string camera_ip = "192.168.1.100";  // FPGA IP address
int camera_port = 5000;                    // FPGA TCP port
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

**FPGA Side:** Initiate frame transmission to the PC IP address on port 5000.

---

## Frame Format Specification

### Packet Structure (with header)
```text
┌──────────────────┬─────────────────────────────────────────┐
│ 4 bytes (uint32) │              Frame Data                 │
│   Frame Size     │         (249,600 bytes)                 │
│  Little-endian   │                                         │
└──────────────────┴─────────────────────────────────────────┘
```

### Frame Data Layout
```text
┌─────────────────────────────┬─────────────────────────────┐
│     Positive Channel        │     Negative Channel        │
│     (124,800 bytes)         │     (124,800 bytes)         │
│   1 bit per pixel           │   1 bit per pixel           │
└─────────────────────────────┴─────────────────────────────┘
```

### Bit Packing (Default: LSB first, Row-major)
```text
Byte 0: [bit7][bit6][bit5][bit4][bit3][bit2][bit1][bit0]
        (msb_first=false: bit0 corresponds to first pixel)

Pixel arrangement (row-major):
  Row 0: pixels 0-1279
  Row 1: pixels 1280-2559
  ...
  Row 779: pixels 997,120-998,399
```

### FPGA Implementation Reference (Pseudocode)
```verilog
// Transmit header (4 bytes, little-endian)
send_byte(frame_size[7:0]);
send_byte(frame_size[15:8]);
send_byte(frame_size[23:16]);
send_byte(frame_size[31:24]);

// Transmit positive channel (124,800 bytes)
for i = 0 to 124799:
    send_byte(positive_channel[i]);

// Transmit negative channel (124,800 bytes)
for i = 0 to 124799:
    send_byte(negative_channel[i]);
```

---

## Troubleshooting

### Connection Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Failed to connect to camera" | Incorrect IP/port or network issue | Verify IP address in config; test with `ping` |
| "Connection closed by server" | FPGA stopped transmitting | Verify FPGA is running and sending data |
| No events in DV viewer | DV connected to wrong port | Connect DV to port 7777 (not 5000) |

### Image Quality Issues

| Symptom | Solution |
|---------|----------|
| Random noise pattern | Set `msb_first = true` |
| Inverted polarity | Set `positive_first = false` |
| 90-degree rotation | Set `row_major = false` |
| Partial image | Verify `width` and `height` match sensor resolution |
| Incomplete frames | Verify `has_header` setting matches FPGA output |

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

# Run simulator
python3 ~/tcp-to-aedat4-converter/test/fake_camera.py

# Run simulator with options
python3 test/fake_camera.py --port 5000 --fps 100

# Launch DV viewer
dv-gui
```

### Network Ports

| Port | Function | Direction |
|------|----------|-----------|
| 5000 | Frame input | Camera/FPGA → Converter |
| 7777 | Event output | Converter → DV Viewer |

### File Locations

| File | Description |
|------|-------------|
| `include/config.hpp` | Configuration settings |
| `build/converter` | Main executable |
| `test/fake_camera.py` | Camera simulator |

---

## Technical Specifications

| Parameter | Value |
|-----------|-------|
| Resolution | 1280 x 780 pixels |
| Frame size | 249,600 bytes |
| Channels | 2 (positive + negative) |
| Target frame rate | 500-1000 FPS |
| Maximum throughput | 250 MB/s |
| Network support | 1GbE, 10GbE |
| Protocol | TCP/IP |
| Output format | AEDAT4 |

---

## Additional Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical design documentation
- Contact: Berk Yilmaz

## License

MIT License
