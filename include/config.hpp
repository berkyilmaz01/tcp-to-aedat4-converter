#pragma once

#include <string>
#include <cstdint>

namespace converter {

/**
 * Protocol type for camera connection
 */
enum class Protocol {
    TCP,    // TCP server - listens for FPGA connection (FPGA connects to us)
    UDP     // UDP receiver - binds to port and receives datagrams
};

/**
 * Helper to convert Protocol enum to string
 */
inline const char* protocolToString(Protocol p) {
    switch (p) {
        case Protocol::TCP: return "TCP";
        case Protocol::UDP: return "UDP";
        default: return "Unknown";
    }
}

/**
 * Configuration for TCP/UDP to AEDAT4 Converter
 * 
 * Configured for FPGA 2-bit packed pixel format:
 *   - Each pixel = 2 bits
 *   - 00 = no event
 *   - 01 = positive polarity (p=1)
 *   - 10 = negative polarity (p=0)
 *   - 11 = unused
 *   - 4 pixels per byte, MSB first (bits 7-6 = pixel 0)
 */
struct Config {

    // =========================================================================
    // FRAME SETTINGS
    // =========================================================================

    int width = 1280;           // Frame width in pixels
    int height = 720;           // Frame height in pixels (FPGA uses 720)

    // Auto-calculated frame size for 2-bit packed pixels
    // Each pixel = 2 bits, so 4 pixels per byte
    int total_pixels() const { return width * height; }
    int frame_size() const { return (total_pixels() + 3) / 4; }  // 230,400 bytes for 1280x720

    // =========================================================================
    // PROTOCOL SELECTION
    // =========================================================================

    Protocol protocol = Protocol::TCP;  // TCP for FPGA connection

    // =========================================================================
    // NETWORK SETTINGS - INPUT (from camera/FPGA)
    // =========================================================================

    // For TCP: Not used (converter is server, listens on all interfaces)
    // For UDP: IP to bind to (use "0.0.0.0" to listen on all interfaces)
    std::string camera_ip = "0.0.0.0";
    int camera_port = 6000;               // Port to listen on (FPGA connects here)

    // Receive buffer size (bytes) - larger = handles bursts better
    int recv_buffer_size = 50 * 1024 * 1024;  // 50 MB

    // =========================================================================
    // UDP-SPECIFIC SETTINGS
    // =========================================================================

    // Maximum UDP packet size to receive
    // Standard: 65535 bytes (max UDP datagram)
    // Jumbo frames on 10G: up to 9000 bytes MTU, ~8972 payload
    // Set this to match your network configuration
    int udp_packet_size = 65535;
    
    // =========================================================================
    // NETWORK SETTINGS - OUTPUT (to DV viewer)
    // =========================================================================
    
    int aedat_port = 7777;      // Port where DV viewer connects
    
    // =========================================================================
    // FRAME HEADER SETTINGS (TCP only)
    // =========================================================================

    // Does the camera send a size header before each frame?
    // FPGA sends raw data without headers
    bool has_header = false;
    
    // Header size in bytes (only used if has_header = true)
    int header_size = 4;
    
    // =========================================================================
    // TIMING SETTINGS
    // =========================================================================
    
    // Microseconds between frames (for timestamp generation)
    // FPGA uses SLICE_PERIOD_US = 10000 (100 FPS)
    // Adjust based on actual frame rate from FPGA
    int64_t frame_interval_us = 10000;
    
    // =========================================================================
    // DEBUG SETTINGS
    // =========================================================================
    
    // Print statistics every N frames (0 = disable)
    int stats_interval = 100;
    
    // Print verbose debug messages
    bool verbose = false;
};

// Global configuration instance
// Modify this in main() or load from file if needed
inline Config config;

} // namespace converter
