#ifndef HTTP_CLIENT_HPP
#define HTTP_CLIENT_HPP

#include <string>
#include <map>

struct HttpResponse {
    int status_code = 0;
    std::string body;
    bool success = false;
    std::string error_message;
};

class HttpClient {
public:
    /**
     * Realiza uma requisição HTTP/1.1 GET síncrona com timeout configurável.
     * Suporta resoluções de nome IPv4/IPv6 e cabeçalhos customizados (ex: X-Auth-Token).
     * Totalmente nativo em C++ (Winsock no Windows / Sockets POSIX no Linux), sem chamadas de sistema ou curl.
     */
    static HttpResponse get(
        const std::string& host,
        int port,
        const std::string& path,
        const std::map<std::string, std::string>& headers = {},
        int timeout_ms = 2500
    );
};

#endif // HTTP_CLIENT_HPP
