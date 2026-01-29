#include "frame_unpacker.hpp"
#include <iostream>
#include <stdexcept>

namespace converter {

FrameUnpacker::FrameUnpacker(const Config& cfg)
    : config_(cfg)
{
    // Pre-compute base pixel index for each byte
    int frame_size = config_.frame_size();
    byte_to_base_pixel_.resize(frame_size);
    
    for (int byte_idx = 0; byte_idx < frame_size; byte_idx++) {
        byte_to_base_pixel_[byte_idx] = byte_idx * 4;  // 4 pixels per byte
    }
}

int FrameUnpacker::getExpectedFrameSize() const
{
    return config_.frame_size();
}

cv::Size FrameUnpacker::getResolution() const
{
    return cv::Size(config_.width, config_.height);
}

size_t FrameUnpacker::unpack(
    const std::vector<uint8_t>& frame_data,
    uint64_t frame_number,
    dv::EventStore& events)
{
    return unpack(frame_data.data(), frame_data.size(), frame_number, events);
}

size_t FrameUnpacker::unpack(
    const uint8_t* frame_data,
    size_t data_size,
    uint64_t frame_number,
    dv::EventStore& events)
{
    // Validate frame size
    int expected_size = getExpectedFrameSize();
    if (static_cast<int>(data_size) < expected_size) {
        std::cerr << "Warning: Frame data size (" << data_size
                  << ") is smaller than expected (" << expected_size << ")" << std::endl;
        return 0;
    }

    // Clear output
    events = dv::EventStore();

    // Calculate timestamp for this frame
    int64_t timestamp = static_cast<int64_t>(frame_number) * config_.frame_interval_us;

    const int width = config_.width;
    const int height = config_.height;
    const int total_pixels = config_.total_pixels();

    // Process each byte (4 pixels per byte)
    // FPGA format: bits 7-6 = pixel 0, bits 5-4 = pixel 1, bits 3-2 = pixel 2, bits 1-0 = pixel 3
    // Values: 00 = no event, 01 = positive (p=1), 10 = negative (p=0), 11 = unused
    
    for (int byte_idx = 0; byte_idx < expected_size; byte_idx++) {
        uint8_t byte_val = frame_data[byte_idx];
        
        // Skip zero bytes entirely - no events in this byte
        // This is a key optimization for sparse event data
        if (byte_val == 0) {
            continue;
        }
        
        // Base pixel index for this byte
        int base_pixel = byte_to_base_pixel_[byte_idx];
        
        // Extract 4 pixels from this byte (MSB first, as per FPGA format)
        // shift = 6, 4, 2, 0 for pixels 0, 1, 2, 3
        for (int px_in_byte = 0; px_in_byte < 4; px_in_byte++) {
            int shift = 6 - (px_in_byte * 2);
            uint8_t pixel_val = (byte_val >> shift) & 0x03;
            
            // Skip if no event (00) or unused (11)
            if (pixel_val == 0 || pixel_val == 3) {
                continue;
            }
            
            // Calculate pixel index
            int pixel_idx = base_pixel + px_in_byte;
            
            // Bounds check (handle last byte which may have padding)
            if (pixel_idx >= total_pixels) {
                continue;
            }
            
            // Calculate x, y coordinates (row-major order)
            int16_t x = static_cast<int16_t>(pixel_idx % width);
            int16_t y = static_cast<int16_t>(pixel_idx / width);
            
            // Determine polarity: 01 = positive (true), 10 = negative (false)
            bool polarity = (pixel_val == 1);
            
            // Add event
            events.emplace_back(timestamp, x, y, polarity);
        }
    }

    if (config_.verbose) {
        std::cout << "Frame " << frame_number << ": unpacked " << events.size() << " events" << std::endl;
    }

    return events.size();
}

} // namespace converter
