#include "tcp_receiver.hpp"
#include <iostream>
#include <cstring>

// Windows doesn't define ssize_t
#ifdef _WIN32
typedef int ssize_t;
#endif

namespace converter {

// Static member initialization
bool TcpReceiver::socket_lib_initialized_ = false;

TcpReceiver::TcpReceiver(const Config& cfg)
    : config_(cfg)
    , server_socket_(INVALID_SOCK)
    , client_socket_(INVALID_SOCK)
    , connected_(false)
    , total_bytes_received_(0)
    , total_frames_received_(0)
{
    initSocketLib();
}

TcpReceiver::~TcpReceiver()
{
    disconnect();
}

TcpReceiver::TcpReceiver(TcpReceiver&& other) noexcept
    : config_(other.config_)
    , server_socket_(other.server_socket_)
    , client_socket_(other.client_socket_)
    , connected_(other.connected_)
    , total_bytes_received_(other.total_bytes_received_)
    , total_frames_received_(other.total_frames_received_)
{
    other.server_socket_ = INVALID_SOCK;
    other.client_socket_ = INVALID_SOCK;
    other.connected_ = false;
}

TcpReceiver& TcpReceiver::operator=(TcpReceiver&& other) noexcept
{
    if (this != &other) {
        disconnect();
        server_socket_ = other.server_socket_;
        client_socket_ = other.client_socket_;
        connected_ = other.connected_;
        total_bytes_received_ = other.total_bytes_received_;
        total_frames_received_ = other.total_frames_received_;
        other.server_socket_ = INVALID_SOCK;
        other.client_socket_ = INVALID_SOCK;
        other.connected_ = false;
    }
    return *this;
}

bool TcpReceiver::initSocketLib()
{
#ifdef _WIN32
    if (!socket_lib_initialized_) {
        WSADATA wsaData;
        int result = WSAStartup(MAKEWORD(2, 2), &wsaData);
        if (result != 0) {
            std::cerr << "WSAStartup failed: " << result << std::endl;
            return false;
        }
        socket_lib_initialized_ = true;
    }
#endif
    return true;
}

void TcpReceiver::cleanupSocketLib()
{
#ifdef _WIN32
    if (socket_lib_initialized_) {
        WSACleanup();
        socket_lib_initialized_ = false;
    }
#endif
}

bool TcpReceiver::connect()
{
    if (connected_) {
        std::cerr << "Already connected" << std::endl;
        return true;
    }
    
    // Close any existing sockets
    disconnect();
    
    // Create server socket
    server_socket_ = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server_socket_ == INVALID_SOCK) {
        std::cerr << "Failed to create server socket: " << SOCKET_ERROR_CODE << std::endl;
        return false;
    }
    
    // Allow address reuse (helps with quick restarts)
    int reuse = 1;
    if (setsockopt(server_socket_, SOL_SOCKET, SO_REUSEADDR,
                   reinterpret_cast<const char*>(&reuse), sizeof(reuse)) < 0) {
        std::cerr << "Warning: Failed to set SO_REUSEADDR" << std::endl;
    }
    
    // Setup server address - bind to all interfaces
    struct sockaddr_in server_addr;
    std::memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(config_.camera_port);
    server_addr.sin_addr.s_addr = INADDR_ANY;  // Bind to all interfaces
    
    // Bind socket
    std::cout << "Binding to port " << config_.camera_port << "..." << std::endl;
    
    if (bind(server_socket_, reinterpret_cast<struct sockaddr*>(&server_addr), sizeof(server_addr)) < 0) {
        std::cerr << "Failed to bind: " << SOCKET_ERROR_CODE << std::endl;
        disconnect();
        return false;
    }
    
    // Listen for connections
    if (listen(server_socket_, 1) < 0) {
        std::cerr << "Failed to listen: " << SOCKET_ERROR_CODE << std::endl;
        disconnect();
        return false;
    }
    
    std::cout << "Listening on port " << config_.camera_port << "..." << std::endl;
    std::cout << "Waiting for FPGA to connect..." << std::endl;
    
    // Accept connection from FPGA
    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);
    
    client_socket_ = accept(server_socket_, reinterpret_cast<struct sockaddr*>(&client_addr), &client_len);
    if (client_socket_ == INVALID_SOCK) {
        std::cerr << "Failed to accept connection: " << SOCKET_ERROR_CODE << std::endl;
        disconnect();
        return false;
    }
    
    // Get client IP for logging
    char client_ip[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, sizeof(client_ip));
    std::cout << "FPGA connected from " << client_ip << ":" << ntohs(client_addr.sin_port) << std::endl;
    
    // Set receive buffer size on client socket
    int rcvbuf = config_.recv_buffer_size;
    if (setsockopt(client_socket_, SOL_SOCKET, SO_RCVBUF, 
                   reinterpret_cast<const char*>(&rcvbuf), sizeof(rcvbuf)) < 0) {
        std::cerr << "Warning: Failed to set receive buffer size" << std::endl;
    }
    
    // Disable Nagle's algorithm for lower latency
    int flag = 1;
    if (setsockopt(client_socket_, IPPROTO_TCP, TCP_NODELAY,
                   reinterpret_cast<const char*>(&flag), sizeof(flag)) < 0) {
        std::cerr << "Warning: Failed to disable Nagle's algorithm" << std::endl;
    }
    
    connected_ = true;
    total_bytes_received_ = 0;
    total_frames_received_ = 0;
    
    std::cout << "Connection established successfully!" << std::endl;
    return true;
}

void TcpReceiver::disconnect()
{
    // Close client socket
    if (client_socket_ != INVALID_SOCK) {
#ifdef _WIN32
        closesocket(client_socket_);
#else
        close(client_socket_);
#endif
        client_socket_ = INVALID_SOCK;
    }
    
    // Close server socket
    if (server_socket_ != INVALID_SOCK) {
#ifdef _WIN32
        closesocket(server_socket_);
#else
        close(server_socket_);
#endif
        server_socket_ = INVALID_SOCK;
    }
    
    connected_ = false;
}

bool TcpReceiver::isConnected() const
{
    return connected_;
}

bool TcpReceiver::receiveExact(uint8_t* buffer, size_t size)
{
    size_t total_received = 0;
    
    while (total_received < size) {
        ssize_t received = recv(client_socket_, 
                                reinterpret_cast<char*>(buffer + total_received),
                                size - total_received, 
                                0);
        
        if (received <= 0) {
            if (received == 0) {
                std::cerr << "Connection closed by FPGA" << std::endl;
            } else {
                std::cerr << "Receive error: " << SOCKET_ERROR_CODE << std::endl;
            }
            connected_ = false;
            return false;
        }
        
        total_received += received;
        total_bytes_received_ += received;
    }
    
    return true;
}

bool TcpReceiver::receiveFrame(std::vector<uint8_t>& buffer)
{
    if (!connected_) {
        std::cerr << "Not connected" << std::endl;
        return false;
    }
    
    int frame_size = getFrameSize();
    
    // If has header, read frame size from header first
    if (config_.has_header) {
        uint32_t header_frame_size = 0;
        
        if (!receiveExact(reinterpret_cast<uint8_t*>(&header_frame_size), config_.header_size)) {
            return false;
        }
        
        // Use header frame size if valid, otherwise use configured size
        if (header_frame_size > 0 && header_frame_size < 100000000) {  // Sanity check: < 100MB
            frame_size = header_frame_size;
        }
        
        if (config_.verbose) {
            std::cout << "Frame header: size = " << frame_size << " bytes" << std::endl;
        }
    }
    
    // Resize buffer and receive frame data
    buffer.resize(frame_size);
    
    if (!receiveExact(buffer.data(), frame_size)) {
        return false;
    }
    
    total_frames_received_++;
    
    if (config_.verbose) {
        std::cout << "Received frame " << total_frames_received_ 
                  << " (" << frame_size << " bytes)" << std::endl;
    }
    
    return true;
}

int TcpReceiver::getFrameSize() const
{
    return config_.frame_size();
}

} // namespace converter
