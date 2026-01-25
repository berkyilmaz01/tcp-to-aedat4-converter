# Testing Strategy for TCP to AEDAT4 Converter

## Overview

This document outlines the comprehensive testing strategy for the TCP to AEDAT4 converter project. The testing approach covers unit tests, integration tests, and manual validation with the fake camera simulator.

## Test Architecture

```
test/
├── unit/
│   ├── test_config.cpp          # Config helper function tests
│   ├── test_frame_unpacker.cpp  # Bit unpacking logic tests
│   └── test_tcp_receiver.cpp    # TCP receiver tests (mock-based)
├── integration/
│   └── test_pipeline.cpp        # End-to-end pipeline tests
├── fixtures/
│   └── test_frames.hpp          # Test data generators
└── fake_camera.py               # Python simulator for manual testing
```

## Test Categories

### 1. Unit Tests

#### Config Tests (`test_config.cpp`)
- `pixels_per_channel()` calculation correctness
- `bytes_per_channel()` calculation correctness
- `frame_size()` calculation correctness
- Edge cases: minimum sizes, large values

#### FrameUnpacker Tests (`test_frame_unpacker.cpp`)
| Test Case | Description |
|-----------|-------------|
| `UnpackEmptyFrame` | All-zero input produces no events |
| `UnpackFullFrame` | All-ones input produces max events |
| `UnpackSinglePixel` | Single bit set produces one event |
| `UnpackKnownPattern` | Verify specific bit patterns |
| `BitOrderingMSB` | Test MSB-first bit extraction |
| `BitOrderingLSB` | Test LSB-first bit extraction |
| `RowMajorLayout` | Test row-major pixel ordering |
| `ColumnMajorLayout` | Test column-major pixel ordering |
| `PositiveFirstChannel` | Test positive-first channel order |
| `NegativeFirstChannel` | Test negative-first channel order |
| `AllConfigurations` | Test all 8 bit ordering combinations |
| `TimestampGeneration` | Verify correct timestamp calculation |
| `InvalidFrameSize` | Reject undersized frames |

#### TcpReceiver Tests (`test_tcp_receiver.cpp`)
- Connection state management
- Statistics tracking (bytes, frames received)
- Disconnect handling

### 2. Integration Tests

#### Pipeline Tests (`test_pipeline.cpp`)
- Receive frame → Unpack → Verify events
- Multiple frames with correct timestamps
- Statistics accuracy

### 3. Manual Testing with Fake Camera

```bash
# Terminal 1: Start converter
./build/converter

# Terminal 2: Start fake camera
python3 test/fake_camera.py --port 5000 --fps 500

# Terminal 3: View in DV (optional)
dv-gui  # Connect to localhost:7777
```

## Test Framework

We use **Google Test** (gtest) for C++ unit tests.

### Building Tests

```bash
mkdir build && cd build
cmake .. -DBUILD_TESTING=ON
make
ctest --output-on-failure
```

### Running Specific Tests

```bash
# Run all tests
./build/test/unit_tests

# Run specific test suite
./build/test/unit_tests --gtest_filter="ConfigTest.*"
./build/test/unit_tests --gtest_filter="FrameUnpackerTest.*"

# Run with verbose output
./build/test/unit_tests --gtest_filter="*" --gtest_print_time=1
```

## Test Data Generation

### Known Pattern Tests

For deterministic testing, we use small frames with known bit patterns:

```cpp
// 8x8 frame (2 channels = 16 bytes total)
// Each channel = 8 bytes (64 pixels / 8 bits per byte)
Config test_config;
test_config.width = 8;
test_config.height = 8;

// Create frame with single pixel set at (0,0)
// LSB first, row-major: bit 0 of byte 0
std::vector<uint8_t> frame(16, 0);
frame[0] = 0x01;  // Pixel (0,0) positive channel
```

### All Configuration Combinations

```cpp
// 8 combinations of (msb_first, positive_first, row_major)
for (bool msb : {false, true}) {
    for (bool pos_first : {false, true}) {
        for (bool row_major : {false, true}) {
            // Test each combination
        }
    }
}
```

## Coverage Goals

| Component | Target Coverage |
|-----------|-----------------|
| Config helpers | 100% |
| FrameUnpacker::unpack() | 100% |
| FrameUnpacker::getBit() | 100% |
| FrameUnpacker::getBitIndex() | 100% |
| TcpReceiver (unit testable parts) | 80% |
| Integration pipeline | Key paths |

## Continuous Integration

### Recommended CI Pipeline

```yaml
stages:
  - build
  - test
  - integration

build:
  script:
    - mkdir build && cd build
    - cmake .. -DBUILD_TESTING=ON
    - make -j$(nproc)

unit_test:
  script:
    - cd build && ctest --output-on-failure

integration_test:
  script:
    - ./build/converter &
    - sleep 1
    - python3 test/fake_camera.py --frames 100 --port 5000
    - # Verify output
```

## Debugging Failed Tests

### Enable Verbose Mode

```cpp
test_config.verbose = true;
```

### Visualize Frame Data

```cpp
void printFrameBits(const std::vector<uint8_t>& data, int width, int height) {
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int bit_idx = y * width + x;
            int byte_idx = bit_idx / 8;
            int bit_off = bit_idx % 8;
            std::cout << ((data[byte_idx] >> bit_off) & 1);
        }
        std::cout << "\n";
    }
}
```

## Performance Testing

For high-throughput validation:

```bash
# Generate frames at max speed
python3 test/fake_camera.py --fps 1000 --duration 60

# Monitor converter output
# Should maintain >500 FPS processing rate
```

## Test Maintenance

- Update tests when Config defaults change
- Add tests for new configuration options
- Keep test frame sizes small (8x8 or 16x16) for readability
- Use parameterized tests for configuration combinations
