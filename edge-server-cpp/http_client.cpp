#include "http_client.hpp"
#include <iostream>
#include <sstream>
#include <vector>
#include <cstring>

#ifdef _WIN32
  #ifndef WIN32_LEAN_AND_MEAN
    #define WIN32_LEAN_AND_MEAN
  #endif
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #pragma comment(lib, "ws2_32.lib")
  using socket_t = SOCKET;
  #define IS_VALIDSOCKET(s) ((s) != INVALID_SOCKET)
  #define CLOSESOCKET(s) closesocket(s)
  #define GETSOCKETERR() WSAGetLastError()
#else
  #include <sys/types.h>
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <arpa/inet.h>
  #include <netdb.h>
  #include <unistd.h>
  using socket_t = int;
  #define IS_VALIDSOCKET(s) ((s) >= 0)
  #define CLOSESOCKET(s) close(s)
  #define GETSOCKETERR() errno
#endif

#ifdef _WIN32
namespace {
    struct WsaSession {
        WsaSession() {
            WSADATA wsa;
            WSAStartup(MAKEWORD(2, 2), &wsa);
        }
        ~WsaSession() {
            WSACleanup();
        }
    };
    static WsaSession g_wsa_session;
}
#endif

HttpResponse HttpClient::get(
    const std::string& host,
    int port,
    const std::string& path,
    const std::map<std::string, std::string>& headers,
    int timeout_ms
) {
    HttpResponse response;

    struct addrinfo hints;
    struct addrinfo* res = nullptr;
    std::memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    std::string port_str = std::to_string(port);
    int status = getaddrinfo(host.c_str(), port_str.c_str(), &hints, &res);
    if (status != 0 || res == nullptr) {
        response.success = false;
        response.error_message = "Falha ao resolver endereço do host: " + host;
        return response;
    }

    socket_t sock = INVALID_SOCKET;
    struct addrinfo* p = nullptr;
    for (p = res; p != nullptr; p = p->ai_next) {
        sock = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
        if (!IS_VALIDSOCKET(sock)) {
            continue;
        }

        // Configuração de timeout de envio e recebimento
#ifdef _WIN32
        DWORD tv = static_cast<DWORD>(timeout_ms);
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&tv), sizeof(tv));
        setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, reinterpret_cast<const char*>(&tv), sizeof(tv));
#else
        struct timeval tv;
        tv.tv_sec = timeout_ms / 1000;
        tv.tv_usec = (timeout_ms % 1000) * 1000;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
        setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#endif

        if (connect(sock, p->ai_addr, static_cast<int>(p->ai_addrlen)) == 0) {
            break; // Conexão estabelecida com sucesso
        }

        CLOSESOCKET(sock);
        sock = INVALID_SOCKET;
    }

    freeaddrinfo(res);

    if (!IS_VALIDSOCKET(sock)) {
        response.success = false;
        response.error_message = "Não foi possível conectar em " + host + ":" + port_str;
        return response;
    }

    // Montagem do frame HTTP/1.1
    std::ostringstream request_stream;
    request_stream << "GET " << path << " HTTP/1.1\r\n";
    request_stream << "Host: " << host << ":" << port_str << "\r\n";
    request_stream << "User-Agent: EdgeServerCpp/1.0\r\n";
    request_stream << "Connection: close\r\n";
    for (const auto& [key, value] : headers) {
        request_stream << key << ": " << value << "\r\n";
    }
    request_stream << "\r\n";

    std::string request_data = request_stream.str();
    int bytes_sent = send(sock, request_data.c_str(), static_cast<int>(request_data.size()), 0);
    if (bytes_sent <= 0) {
        CLOSESOCKET(sock);
        response.success = false;
        response.error_message = "Erro ao enviar dados pela conexão TCP.";
        return response;
    }

    // Leitura da resposta
    std::string raw_response;
    char buffer[1024];
    int bytes_read = 0;
    while ((bytes_read = recv(sock, buffer, sizeof(buffer) - 1, 0)) > 0) {
        buffer[bytes_read] = '\0';
        raw_response.append(buffer, bytes_read);
    }

    CLOSESOCKET(sock);

    if (raw_response.empty()) {
        response.success = false;
        response.error_message = "Resposta vazia ou conexão encerrada prematuramente.";
        return response;
    }

    // Parse do status code HTTP (ex: HTTP/1.1 200 OK)
    size_t line_end = raw_response.find("\r\n");
    if (line_end != std::string::npos) {
        std::string status_line = raw_response.substr(0, line_end);
        std::istringstream line_stream(status_line);
        std::string http_version;
        int code = 0;
        if (line_stream >> http_version >> code) {
            response.status_code = code;
        }
    }

    // Separação de headers e payload body
    size_t body_pos = raw_response.find("\r\n\r\n");
    if (body_pos != std::string::npos) {
        response.body = raw_response.substr(body_pos + 4);
    } else {
        response.body = raw_response;
    }

    response.success = (response.status_code >= 200 && response.status_code < 400);
    return response;
}
