#include "local-admission.h"

#include <arpa/inet.h>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cctype>
#include <map>
#include <string_view>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <future>
#include <memory>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

#include "arm64_context.h"
#include "jni_env.h"
#include "shim.h"

namespace {
using Clock = std::chrono::steady_clock;
constexpr auto requestTimeout = std::chrono::milliseconds(2500);
constexpr size_t maximumResponse = 256 * 1024;
constexpr char productionHTTPS[] = "https://live.saintjoy.co.kr";
constexpr char productionHTTP[] = "http://live.saintjoy.co.kr";
constexpr size_t maximumUpload = 256 * 1024;
struct Endpoint {
    std::string host;
    uint16_t port = 0;
    uint32_t address = 0;
};

using Headers = std::map<std::string, std::string>;

struct Socket {
    int fd = -1;
    ~Socket() { if (fd != -1) ::close(fd); }
};

bool waitFor(int fd, short events, Clock::time_point deadline) {
    pollfd descriptor{fd, events, 0};
    for (auto now = Clock::now(); now < deadline; now = Clock::now()) {
        auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - now).count();
        const int result = ::poll(&descriptor, 1, int(remaining + 1));
        if (result > 0) return (descriptor.revents & (events | POLLHUP)) != 0;
        if (result == 0 || errno != EINTR) return false;
    }
    return false;
}

Endpoint mockEndpoint() {
    const char* portText = std::getenv("ACIES_LOCAL_MOCK_PORT");
    const char* hostText = std::getenv("ACIES_LOCAL_MOCK_HOST");
    if (!portText || !*portText) return {};
    if (!hostText || !*hostText) hostText = "127.0.0.1";
    char* end = nullptr;
    const long port = std::strtol(portText, &end, 10);
    in_addr ip{};
    if (*end || port <= 0 || port > 65535 || inet_pton(AF_INET, hostText, &ip) != 1) return {};
    const auto address = ntohl(ip.s_addr);
    const bool privateAddress = address == INADDR_LOOPBACK ||
        (address & 0xff000000) == 0x0a000000 ||
        (address & 0xfff00000) == 0xac100000 ||
        (address & 0xffff0000) == 0xc0a80000;
    if (!privateAddress) return {};
    return {hostText, uint16_t(port), ip.s_addr};
}

std::string ownedPath(const Endpoint& endpoint, const std::string& url) {
    const auto localOrigin = "http://" + endpoint.host + ":" + std::to_string(endpoint.port);
    size_t originLength = 0;
    for (const std::string_view origin : {std::string_view(productionHTTPS),
                                          std::string_view(productionHTTP),
                                          std::string_view(localOrigin)}) {
        if (url.compare(0, origin.size(), origin) == 0) {
            originLength = origin.size();
            break;
        }
    }
    if (!originLength || url.size() <= originLength) return {};
    const auto path = url.substr(originLength);
    if (path.rfind("/api/client/", 0) != 0 && path.rfind("/api/client-secure/", 0) != 0) return {};
    if (path.size() > 2048 || path.find("..") != std::string::npos ||
        path.find("//") != std::string::npos) return {};
    for (unsigned char character : path) {
        if (!std::isalnum(character) && std::strchr("/._-?=&%", character) == nullptr) return {};
    }
    return path;
}

LocalAdmissionReply fetchAdmission(uint64_t target, Endpoint endpoint, const std::string& path,
                                   const std::string& method, const Headers& headers,
                                   const std::string& body) {
    const LocalAdmissionReply failed{target, 0, {}};
    if (!endpoint.port || path.empty() || body.size() > maximumUpload) return failed;
    const auto deadline = Clock::now() + requestTimeout;
    Socket socket{::socket(AF_INET, SOCK_STREAM, 0)};
    if (socket.fd == -1 || ::fcntl(socket.fd, F_SETFL, O_NONBLOCK) == -1) return failed;
    int noSignal = 1;
    if (::setsockopt(socket.fd, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, sizeof(noSignal)) == -1)
        return failed;

    sockaddr_in address{};
    address.sin_len = sizeof(address);
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = endpoint.address;
    address.sin_port = htons(endpoint.port);
    if (::connect(socket.fd, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) == -1) {
        if (errno != EINPROGRESS || !waitFor(socket.fd, POLLOUT, deadline)) return failed;
        int error = 0;
        socklen_t size = sizeof(error);
        if (::getsockopt(socket.fd, SOL_SOCKET, SO_ERROR, &error, &size) == -1 || error) return failed;
    }

    std::string request = method + " " + path + " HTTP/1.0\r\nHost: " + endpoint.host + ":" +
        std::to_string(endpoint.port) + "\r\nConnection: close\r\n";
    for (const auto& header : headers) request += header.first + ": " + header.second + "\r\n";
    request += "Content-Length: " + std::to_string(body.size()) + "\r\n\r\n" + body;
    size_t sent = 0;
    while (sent < request.size() && waitFor(socket.fd, POLLOUT, deadline)) {
        const auto result = ::send(socket.fd, request.data() + sent, request.size() - sent, 0);
        if (result > 0) sent += size_t(result);
        else if (result < 0 && errno != EINTR && errno != EAGAIN) return failed;
    }
    if (sent != request.size()) return failed;

    std::string response;
    bool closed = false;
    char chunk[8192];
    while (waitFor(socket.fd, POLLIN, deadline)) {
        const auto size = ::recv(socket.fd, chunk, sizeof(chunk), 0);
        if (size == 0) {
            closed = true;
            break;
        }
        if (size < 0) {
            if (errno == EAGAIN || errno == EINTR) continue;
            return failed;
        }
        if (response.size() + size_t(size) > maximumResponse) return failed;
        response.append(chunk, size_t(size));
    }

    int status = 0;
    const auto bodyStart = response.find("\r\n\r\n");
    if (!closed || bodyStart == std::string::npos ||
        std::sscanf(response.c_str(), "HTTP/%*u.%*u %d", &status) != 1 || status < 200 ||
        status > 599 || (status >= 300 && status < 400)) return failed;
    return {target, status, response.substr(bodyStart + 4)};
}

struct Request {
    std::string url;
    std::string method;
    std::string body;
    Headers headers;
};
struct Connection {
    std::shared_ptr<Request> request;
    uint64_t target;
    bool started = false;
    bool cancelled = false;
};
struct Pending {
    std::shared_ptr<Connection> connection;
    std::future<LocalAdmissionReply> result;
};
std::unordered_map<uint64_t, std::shared_ptr<Request>> requests;
std::unordered_map<uint64_t, std::shared_ptr<Connection>> connections;
std::vector<Pending> pending;
std::unordered_map<uint64_t, std::string> byteArrayContents;
const std::string* deliveredBody = nullptr;

enum Token {
    requestClass, bridgeClass,
    createRequest, setBody, setHeader, getURL, createHandle, startHandle, destroyHandle, cancelHandle, dropBridge
};
uint8_t tokens[11]{};
uint64_t token(Token value) { return reinterpret_cast<uint64_t>(&tokens[value]); }

bool textIs(const char* a, const char* b) { return a && std::strcmp(a, b) == 0; }

const char* stringArgument(uint64_t ref) {
    return arc_jni_owns(ref) ? reinterpret_cast<const char*>(ref) : "";
}

struct Args {
    alignas(uint64_t) uint8_t cursor[32] = {};
    explicit Args(Arm64Ctx* context) {
        if (context->x[3]) std::memcpy(cursor, reinterpret_cast<void*>(context->x[3]), sizeof(cursor));
    }
    uint64_t next() { return arc::ShimVaNextInt(cursor); }
};

template <unsigned slot>
ArcCtxFn previous = nullptr;

void findClass(Arm64Ctx* c) {
    const auto* name = reinterpret_cast<const char*>(c->x[1]);
    if (textIs(name, "kr/co/brgames/cdk/CSURLRequest")) c->x[0] = token(requestClass);
    else if (textIs(name, "kr/co/brgames/cdk/CSURLConnectionBridge")) c->x[0] = token(bridgeClass);
    else previous<6>(c);
}

bool tracks(uint64_t ref) {
    return ref == token(requestClass) || ref == token(bridgeClass) || requests.count(ref) ||
           connections.count(ref);
}

void globalRef(Arm64Ctx* c) {
    if (tracks(c->x[1])) c->x[0] = c->x[1];
    else previous<21>(c);
}
void deleteGlobal(Arm64Ctx* c) {
    if (tracks(c->x[1])) {
        requests.erase(c->x[1]);
        c->x[0] = 0;
    } else previous<22>(c);
}
void deleteLocal(Arm64Ctx* c) {
    byteArrayContents.erase(c->x[1]);
    if (tracks(c->x[1])) c->x[0] = 0;
    else previous<23>(c);
}

void getMethod(Arm64Ctx* c) {
    const auto* name = reinterpret_cast<const char*>(c->x[2]);
    const auto* signature = reinterpret_cast<const char*>(c->x[3]);
    if (c->x[1] == token(requestClass)) {
        if (textIs(name, "setBody") && textIs(signature, "([B)V")) {
            c->x[0] = token(setBody);
            return;
        }
        if (textIs(name, "setHeaderField") &&
            textIs(signature, "(Ljava/lang/String;Ljava/lang/String;)V")) {
            c->x[0] = token(setHeader);
            return;
        }
        if (textIs(name, "URL") && textIs(signature, "()Ljava/lang/String;")) {
            c->x[0] = token(getURL);
            return;
        }
    }
    previous<33>(c);
}

void getStaticMethod(Arm64Ctx* c) {
    const auto* name = reinterpret_cast<const char*>(c->x[2]);
    const auto* signature = reinterpret_cast<const char*>(c->x[3]);
    if (c->x[1] == token(requestClass) && textIs(name, "create") &&
        textIs(signature, "(Ljava/lang/String;Ljava/lang/String;ZF)Lkr/co/brgames/cdk/CSURLRequest;")) {
        c->x[0] = token(createRequest);
        return;
    }
    if (c->x[1] == token(bridgeClass)) {
        if (textIs(name, "createHandle")) { c->x[0] = token(createHandle); return; }
        if (textIs(name, "start")) { c->x[0] = token(startHandle); return; }
        if (textIs(name, "destroyHandle")) { c->x[0] = token(destroyHandle); return; }
        if (textIs(name, "cancel")) { c->x[0] = token(cancelHandle); return; }
        if (textIs(name, "dispose")) { c->x[0] = token(dropBridge); return; }
    }
    previous<113>(c);
}

void staticObject(Arm64Ctx* c) {
    if (c->x[2] == token(createRequest)) {
        Args args(c);
        auto request = std::make_shared<Request>();
        request->url = stringArgument(args.next());
        request->method = stringArgument(args.next());
        c->x[0] = reinterpret_cast<uint64_t>(request.get());
        requests.emplace(c->x[0], std::move(request));
        return;
    }
    if (c->x[2] == token(createHandle)) {
        Args args(c);
        const auto found = requests.find(args.next());
        const auto target = args.next();
        c->x[0] = 0;
        if (found != requests.end() && target) {
            auto connection = std::make_shared<Connection>(Connection{found->second, target});
            c->x[0] = reinterpret_cast<uint64_t>(connection.get());
            connections.emplace(c->x[0], std::move(connection));
        }
        return;
    }
    previous<115>(c);
}

void objectMethod(Arm64Ctx* c) {
    const auto found = requests.find(c->x[1]);
    if (c->x[2] == token(getURL) && found != requests.end()) {
        c->x[0] = arc_jni_string(found->second->url.c_str());
        return;
    }
    previous<35>(c);
}

bool headerAllowed(const std::string& key, const std::string& value) {
    if (key.empty() || key.size() > 80 || value.size() > 8192) return false;
    for (unsigned char character : key) {
        if (!std::isalnum(character) && character != '-') return false;
    }
    for (const char* name : {"host", "connection", "content-length", "transfer-encoding", "proxy-authorization"}) {
        if (strcasecmp(key.c_str(), name) == 0) return false;
    }
    for (unsigned char character : value) {
        if (character < 32 || character == 127) return false;
    }
    return true;
}

void voidMethod(Arm64Ctx* c) {
    const auto found = requests.find(c->x[1]);
    if (found != requests.end()) {
        Args args(c);
        if (c->x[2] == token(setBody)) {
            const auto handle = args.next();
            const auto data = byteArrayContents.find(handle);
            found->second->body = data != byteArrayContents.end() ? data->second : stringArgument(handle);
            c->x[0] = 0;
            return;
        }
        if (c->x[2] == token(setHeader)) {
            const std::string name = stringArgument(args.next());
            const std::string value = stringArgument(args.next());
            if (headerAllowed(name, value)) found->second->headers[name] = value;
            c->x[0] = 0;
            return;
        }
    }
    previous<62>(c);
}

void putByteArrayRegion(Arm64Ctx* c) {
    const size_t offset = c->x[2], length = c->x[3];
    if (c->x[1] && c->x[4] && length && offset <= maximumUpload && length <= maximumUpload - offset) {
        if (byteArrayContents.size() > 128) byteArrayContents.clear();
        auto& bytes = byteArrayContents[c->x[1]];
        bytes.resize(std::max(bytes.size(), offset + length));
        std::memcpy(bytes.data() + offset, reinterpret_cast<const void*>(c->x[4]), length);
    }
    previous<208>(c);
}

void staticVoid(Arm64Ctx* c) {
    const auto method = c->x[2];
    if (method == token(dropBridge)) {
        for (auto& item : connections) item.second->cancelled = true;
        connections.clear();
        requests.clear();
        c->x[0] = 0;
        return;
    }
    if (method != token(startHandle) && method != token(destroyHandle) &&
        method != token(cancelHandle)) {
        previous<142>(c);
        return;
    }

    Args args(c);
    const auto found = connections.find(args.next());
    c->x[0] = 0;
    if (found == connections.end()) return;
    const auto conn = found->second;
    if (method != token(startHandle)) {
        conn->cancelled = true;
        if (method == token(destroyHandle)) connections.erase(found);
        return;
    }
    if (conn->started) return;
    conn->started = true;
    const Request& request = *conn->request;
    auto endpoint = mockEndpoint();
    const auto path = endpoint.port && (request.method == "GET" || request.method == "POST")
        ? ownedPath(endpoint, request.url) : std::string();
    const auto policy = path.empty() ? std::launch::deferred : std::launch::async;
    pending.push_back({conn, std::async(policy, fetchAdmission, conn->target, endpoint, path,
                                        request.method, request.headers, request.body)});
    std::fprintf(stderr, "[local HTTP] %s %s, %zu original request bytes\n",
                 request.method.c_str(), path.empty() ? "(unrouted)" : path.c_str(),
                 request.body.size());
}

void arrayLength(Arm64Ctx* c) {
    if (deliveredBody && c->x[1] == reinterpret_cast<uint64_t>(deliveredBody))
        c->x[0] = deliveredBody->size();
    else previous<171>(c);
}

void byteArrayRegion(Arm64Ctx* c) {
    if (deliveredBody && c->x[1] == reinterpret_cast<uint64_t>(deliveredBody)) {
        const size_t offset = c->x[2], size = c->x[3];
        if (offset <= deliveredBody->size() && size <= deliveredBody->size() - offset && c->x[4])
            std::memcpy(reinterpret_cast<void*>(c->x[4]), deliveredBody->data() + offset, size);
        c->x[0] = 0;
    } else previous<200>(c);
}

template <unsigned slot>
void install(const char* name, ArcCtxFn callback) {
    auto** tablePointer = reinterpret_cast<uint64_t**>(arc_jni_env());
    auto* table = *tablePointer;
    previous<slot> = reinterpret_cast<ArcCtxFn>(table[slot]);
    table[slot] = reinterpret_cast<uint64_t>(callback);
    arc_register_ctx_native(table[slot], name, callback);
}
}

void aciesInstallLocalAdmissionJNI() {
    install<6>("FindClass.admission", &findClass);
    install<21>("NewGlobalRef.admission", &globalRef);
    install<22>("DeleteGlobalRef.admission", &deleteGlobal);
    install<23>("DeleteLocalRef.admission", &deleteLocal);
    install<33>("GetMethodID.admission", &getMethod);
    install<35>("CallObjectMethodV.admission", &objectMethod);
    install<62>("CallVoidMethodV.admission", &voidMethod);
    install<113>("GetStaticMethodID.admission", &getStaticMethod);
    install<115>("CallStaticObjectMethodV.admission", &staticObject);
    install<142>("CallStaticVoidMethodV.admission", &staticVoid);
    install<171>("GetArrayLength.admission", &arrayLength);
    install<200>("GetByteArrayRegion.admission", &byteArrayRegion);
    install<208>("SetByteArrayRegion.admission", &putByteArrayRegion);
}

bool aciesTakeLocalAdmissionReply(LocalAdmissionReply& reply) {
    for (auto it = pending.begin(); it != pending.end();) {
        const auto status = it->result.wait_for(std::chrono::milliseconds(0));
        if (status == std::future_status::timeout) {
            ++it;
            continue;
        }
        const bool deliver = !it->connection->cancelled;
        reply = it->result.get();
        it = pending.erase(it);
        if (deliver) return true;
    }
    return false;
}

bool aciesLocalReplyStillActive(uint64_t target) {
    for (const auto& entry : connections) {
        const auto& connection = entry.second;
        if (connection->target == target && !connection->cancelled) return true;
    }
    return false;
}

uint64_t aciesSetLocalAdmissionByteArray(const std::string* body) {
    deliveredBody = body;
    return reinterpret_cast<uint64_t>(deliveredBody);
}
