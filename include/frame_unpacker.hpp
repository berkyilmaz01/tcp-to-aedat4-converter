#pragma once

#include "config.hpp"
#include <dv-processing/core/event.hpp>
#include <vector>
#include <cstdint>

namespace converter {

/**
 * Frame Unpacker class for 2-bit packed pixel format
 *
 * Converts binary 2-bit packed frames from FPGA into dv::EventStore.
 * 
 * Input format (FPGA 2-bit packed):
 *   - Each pixel = 2 bits
 *   - 4 pixels per byte, MSB first:
 *     Byte: [pixel0:2][pixel1:2][pixel2:2][pixel3:2]
 *           bits 7-6   bits 5-4   bits 3-2   bits 1-0
 *   
 *   - Pixel values:
 *     00 = no event
 *     01 = positive polarity (p=1, brightness increased)
 *     10 = negative polarity (p=0, brightness decreased)
 *     11 = unused (treated as no event)
 *   
 *   - Frame size: (width * height + 3) / 4 bytes
 *   - For 1280x720: 230,400 bytes
 *
 * Output format:
 *   - dv::EventStore containing events with (timestamp, x, y, polarity)
 */
class FrameUnpacker {
public:
    /**
     * Constructor
     * @param cfg Configuration reference
     */
    explicit FrameUnpacker(const Config& cfg);

    /**
     * Unpack a binary frame into events
     *
     * @param frame_data Raw binary frame data
     * @param frame_number Frame sequence number (for timestamp generation)
     * @param events Output event store (will be cleared first)
     * @return Number of events unpacked
     */
    size_t unpack(
        const std::vector<uint8_t>& frame_data,
        uint64_t frame_number,
        dv::EventStore& events
    );

    /**
     * Unpack a binary frame into events (pointer version)
     *
     * @param frame_data Raw binary frame data pointer
     * @param data_size Size of frame data in bytes
     * @param frame_number Frame sequence number (for timestamp generation)
     * @param events Output event store (will be cleared first)
     * @return Number of events unpacked
     */
    size_t unpack(
        const uint8_t* frame_data,
        size_t data_size,
        uint64_t frame_number,
        dv::EventStore& events
    );

    /**
     * Get expected frame size in bytes
     * @return Frame size (230,400 bytes for 1280x720)
     */
    int getExpectedFrameSize() const;

    /**
     * Get resolution
     * @return Resolution as cv::Size
     */
    cv::Size getResolution() const;

private:
    const Config& config_;
    
    // Pre-computed coordinate lookup for fast pixel index to (x, y) conversion
    // For each byte index, stores the base pixel index
    std::vector<int32_t> byte_to_base_pixel_;
};

} // namespace converter
