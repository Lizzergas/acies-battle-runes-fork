#include "gateway-imports.h"

#include <arpa/inet.h>
#include <cerrno>
#include <cstddef>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

namespace {

constexpr uint16_t androidInet = 2;
constexpr uint16_t androidInet6 = 10;
constexpr int androidSocketLevel = 1;
constexpr int androidNonblocking = 0x800;
constexpr int androidCloseOnExec = 0x80000;
constexpr int androidWouldBlock = 11;

struct AndroidAddress4 {
    uint16_t family, port;
    in_addr address;
    uint8_t padding[8];
};
struct AndroidAddress6 {
    uint16_t family, port;
    uint32_t flow;
    in6_addr address;
    uint32_t scope;
};
struct AndroidAddrInfo {
    int flags, family, socktype, protocol;
    uint32_t addressLength;
    char* canonicalName;
    void* address;
    AndroidAddrInfo* next;
};
struct AndroidTimeval {
    int64_t seconds, microseconds;
};
struct AndroidAddrInfoStorage {
    AndroidAddrInfo info;
    union {
        AndroidAddress4 v4;
        AndroidAddress6 v6;
    } address;
};
static_assert(sizeof(AndroidAddress4) == 16 && sizeof(AndroidAddress6) == 28);
static_assert(offsetof(AndroidAddrInfo, address) == 32 && offsetof(AndroidAddrInfo, next) == 40);
static_assert(sizeof(fd_set) == 128);

struct Endpoint {
    int family = AF_UNSPEC;
    uint16_t port = 0;
    in_addr v4{};
    in6_addr v6{};
    const char* host = nullptr;
};

bool parsePort(const char* text, uint16_t& result) {
    if (!text || !*text) return false;
    unsigned value = 0;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9') return false;
        value = value * 10 + unsigned(*text - '0');
        if (value > 65535) return false;
    }
    result = static_cast<uint16_t>(value);
    return value != 0;
}

Endpoint configuredEndpoint() {
    Endpoint endpoint;
    const char* host = std::getenv("ACIES_LOCAL_MOCK_HOST");
    const char* port = std::getenv("ACIES_LOCAL_MOCK_GATEWAY_PORT");
    if (!host || !parsePort(port, endpoint.port)) return {};
    // The device test has one owned LAN destination. Other ports are only for loopback tests.
    if (std::strcmp(host, "192.168.0.153") == 0 && endpoint.port == 19091) {
        endpoint.family = AF_INET;
    } else if (std::strcmp(host, "127.0.0.1") == 0) {
        endpoint.family = AF_INET;
    } else if (std::strcmp(host, "::1") == 0) {
        endpoint.family = AF_INET6;
    } else {
        return {};
    }
    endpoint.host = host;
    if (endpoint.family == AF_INET) inet_pton(AF_INET, host, &endpoint.v4);
    else inet_pton(AF_INET6, host, &endpoint.v6);
    return endpoint;
}

int toAndroidErrno(int code) {
    // Darwin's contiguous socket errno range differs from Linux by 50, aside from a few connect states.
    if (code >= ENOTSOCK && code <= ECONNREFUSED) return code + 50;
    switch (code) {
        case EAGAIN: return androidWouldBlock;
        case EINPROGRESS: return 115;
        case EALREADY: return 114;
        case EHOSTDOWN: return 112;
        case EHOSTUNREACH: return 113;
        default: return code;
    }
}

int fail(int hostError) {
    // androidrecomp's __errno resolver returns the native per-thread errno slot.
    errno = toAndroidErrno(hostError);
    return -1;
}

int addressFamily(int family) {
    if (family == androidInet) return AF_INET;
    if (family == androidInet6) return AF_INET6;
    return AF_UNSPEC;
}

int guestGetAddrInfo(const char* host, const char* service, const AndroidAddrInfo* hints, AndroidAddrInfo** result) {
    if (!result) return EAI_FAIL;
    *result = nullptr;
    const Endpoint endpoint = configuredEndpoint();
    uint16_t port = 0;
    if (!host || !endpoint.host || std::strcmp(host, endpoint.host) ||
        (service && (!parsePort(service, port) || port != endpoint.port))) return EAI_NONAME;
    if (hints && hints->socktype != 0 && hints->socktype != SOCK_STREAM) return EAI_SOCKTYPE;
    if (hints && hints->protocol != 0 && hints->protocol != IPPROTO_TCP) return EAI_SERVICE;
    const int family = hints && hints->family != 0 ? addressFamily(hints->family) : endpoint.family;
    if (family == AF_UNSPEC || (family == AF_INET && endpoint.family == AF_INET6)) return EAI_FAMILY;

    auto* storage = static_cast<AndroidAddrInfoStorage*>(calloc(1, sizeof(AndroidAddrInfoStorage)));
    if (!storage) return EAI_MEMORY;
    AndroidAddrInfo& entry = storage->info;
    entry.flags = hints ? hints->flags : 0;
    entry.family = family == AF_INET ? androidInet : androidInet6;
    entry.socktype = SOCK_STREAM;
    entry.protocol = IPPROTO_TCP;
    entry.address = &storage->address;
    if (entry.flags & 2) {
        entry.canonicalName = strdup(host);
        if (!entry.canonicalName) { free(storage); return EAI_MEMORY; }
    }
    if (family == AF_INET) {
        entry.addressLength = sizeof(AndroidAddress4);
        storage->address.v4 = {androidInet, htons(port), endpoint.v4, {}};
    } else {
        entry.addressLength = sizeof(AndroidAddress6);
        auto& v6 = storage->address.v6;
        v6.family = androidInet6;
        v6.port = htons(port);
        if (endpoint.family == AF_INET6) v6.address = endpoint.v6;
        else {
            v6.address.s6_addr[10] = 0xff;
            v6.address.s6_addr[11] = 0xff;
            memcpy(v6.address.s6_addr + 12, &endpoint.v4, sizeof(endpoint.v4));
        }
    }
    *result = &entry;
    return 0;
}

void guestFreeAddrInfo(AndroidAddrInfo* answer) {
    while (answer) {
        AndroidAddrInfo* next = answer->next;
        free(answer->canonicalName);
        free(answer);
        answer = next;
    }
}

bool allowedAddress(const sockaddr_storage& address, const Endpoint& endpoint) {
    if (address.ss_family == AF_INET) {
        if (endpoint.family != AF_INET) return false;
        const auto& v4 = reinterpret_cast<const sockaddr_in&>(address);
        return v4.sin_port == htons(endpoint.port) && v4.sin_addr.s_addr == endpoint.v4.s_addr;
    }
    if (address.ss_family != AF_INET6) return false;
    const auto& v6 = reinterpret_cast<const sockaddr_in6&>(address);
    if (v6.sin6_port != htons(endpoint.port) || v6.sin6_scope_id != 0) return false;
    if (endpoint.family == AF_INET6) return !memcmp(&v6.sin6_addr, &endpoint.v6, sizeof(endpoint.v6));
    return endpoint.family == AF_INET && IN6_IS_ADDR_V4MAPPED(&v6.sin6_addr) &&
        !memcmp(v6.sin6_addr.s6_addr + 12, &endpoint.v4, sizeof(endpoint.v4));
}

socklen_t translateAddress(const void* raw, uint32_t length, sockaddr_storage& native) {
    uint16_t family;
    if (!raw || length < sizeof(family)) return 0;
    memcpy(&family, raw, sizeof(family));
    if (family == androidInet && length >= sizeof(AndroidAddress4)) {
        AndroidAddress4 guest;
        memcpy(&guest, raw, sizeof(guest));
        auto& v4 = reinterpret_cast<sockaddr_in&>(native);
        v4.sin_len = sizeof(v4);
        v4.sin_family = AF_INET;
        v4.sin_port = guest.port;
        v4.sin_addr = guest.address;
        return sizeof(v4);
    }
    if (family == androidInet6 && length >= sizeof(AndroidAddress6)) {
        AndroidAddress6 guest;
        memcpy(&guest, raw, sizeof(guest));
        auto& v6 = reinterpret_cast<sockaddr_in6&>(native);
        v6.sin6_len = sizeof(v6);
        v6.sin6_family = AF_INET6;
        v6.sin6_port = guest.port;
        v6.sin6_flowinfo = guest.flow;
        v6.sin6_addr = guest.address;
        v6.sin6_scope_id = guest.scope;
        return sizeof(v6);
    }
    return 0;
}

int guestSocket(int family, int type, int protocol) {
    if (!configuredEndpoint().host) return fail(EACCES);
    const int nativeFamily = addressFamily(family);
    if (nativeFamily == AF_UNSPEC) return fail(EAFNOSUPPORT);
    constexpr int streamFlags = SOCK_STREAM | androidNonblocking | androidCloseOnExec;
    if ((type & ~streamFlags) || !(type & SOCK_STREAM) || (protocol != 0 && protocol != IPPROTO_TCP))
        return fail(EPROTONOSUPPORT);
    const int fd = socket(nativeFamily, SOCK_STREAM, protocol);
    if (fd < 0) return fail(errno);
    int one = 1, zero = 0;
    if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one)) < 0 ||
        (nativeFamily == AF_INET6 && setsockopt(fd, IPPROTO_IPV6, IPV6_V6ONLY, &zero, sizeof(zero)) < 0) ||
        ((type & androidNonblocking) && fcntl(fd, F_SETFL, O_NONBLOCK) < 0) ||
        ((type & androidCloseOnExec) && fcntl(fd, F_SETFD, FD_CLOEXEC) < 0)) {
        const int error = errno;
        close(fd);
        return fail(error);
    }
    return fd;
}

int guestConnect(int fd, const void* address, uint32_t length) {
    sockaddr_storage native{};
    const socklen_t size = translateAddress(address, length, native);
    if (!size) return fail(EAFNOSUPPORT);
    const Endpoint endpoint = configuredEndpoint();
    if (!allowedAddress(native, endpoint)) return fail(EACCES);
    const int result = connect(fd, reinterpret_cast<sockaddr*>(&native), size);
    const int error = result < 0 ? errno : 0;
    if (std::getenv("ACIES_TRACE_LOCAL_GATEWAY"))
        fprintf(stderr, "local gateway connect %s:%u family=%u host_errno=%d guest_errno=%d\n",
                endpoint.host, unsigned(endpoint.port), unsigned(native.ss_family), error, toAndroidErrno(error));
    return result < 0 ? fail(error) : result;
}

int guestFcntl(int fd, int cmd, int value) {
    int result;
    switch (cmd) {
        case 1: result = fcntl(fd, F_GETFD); break;
        case 2: result = fcntl(fd, F_SETFD, value & FD_CLOEXEC); break;
        case 3:
            result = fcntl(fd, F_GETFL);
            if (result >= 0) return (result & O_ACCMODE) | ((result & O_NONBLOCK) ? androidNonblocking : 0);
            break;
        case 4:
            result = fcntl(fd, F_GETFL);
            if (result >= 0) {
                const int flags = (result & ~O_NONBLOCK) | ((value & androidNonblocking) ? O_NONBLOCK : 0);
                result = fcntl(fd, F_SETFL, flags);
            }
            break;
        default: return fail(EINVAL);
    }
    return result < 0 ? fail(errno) : result;
}

int guestSetSockOpt(int fd, int level, int option, const void* value, uint32_t length) {
    int result;
    if (level == androidSocketLevel && option == 13 && length == sizeof(linger)) {
        result = setsockopt(fd, SOL_SOCKET, SO_LINGER, value, length);
    } else if (level == IPPROTO_TCP && option == 1 && length == sizeof(int)) {
        result = setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, value, length);
    } else {
        return fail(ENOPROTOOPT);
    }
    return result < 0 ? fail(errno) : result;
}

int guestGetSockOpt(int fd, int level, int option, void* value, uint32_t* length) {
    if (level != androidSocketLevel || (option != 3 && option != 4) || !value || !length ||
        *length < sizeof(int)) return fail(ENOPROTOOPT);
    socklen_t size = sizeof(int);
    int native = 0;
    const int result = getsockopt(fd, SOL_SOCKET, option == 3 ? SO_TYPE : SO_ERROR, &native, &size);
    if (result < 0) return fail(errno);
    *length = size;
    const int guest = option == 4 ? toAndroidErrno(native) : native;
    memcpy(value, &guest, size);
    return 0;
}

bool allowedPeer(int fd) {
    sockaddr_storage peer{};
    socklen_t length = sizeof(peer);
    if (getpeername(fd, reinterpret_cast<sockaddr*>(&peer), &length) < 0) {
        fail(errno);
        return false;
    }
    if (allowedAddress(peer, configuredEndpoint())) return true;
    fail(EACCES);
    return false;
}

int messageFlags(int flags) {
    constexpr int accepted = 0x1 | 0x2 | 0x40 | 0x100 | 0x4000;
    if (flags & ~accepted) return -1;
    int result = 0;
    if (flags & 0x1) result |= MSG_OOB;
    if (flags & 0x2) result |= MSG_PEEK;
    if (flags & 0x40) result |= MSG_DONTWAIT;
    if (flags & 0x100) result |= MSG_WAITALL;
    return result;  // SO_NOSIGPIPE already implements Linux MSG_NOSIGNAL.
}

ssize_t guestReceive(int fd, void* data, size_t length, int flags) {
    const int native = messageFlags(flags);
    if (native < 0) return fail(EINVAL);
    if (!allowedPeer(fd)) return -1;
    const ssize_t result = recv(fd, data, length, native);
    return result < 0 ? fail(errno) : result;
}

ssize_t guestSend(int fd, const void* data, size_t length, int flags) {
    const int native = messageFlags(flags);
    if (native < 0) return fail(EINVAL);
    if (!allowedPeer(fd)) return -1;
    const ssize_t result = send(fd, data, length, native);
    return result < 0 ? fail(errno) : result;
}

bool validFdSet(int fd, size_t size) {
    return fd >= 0 && fd < FD_SETSIZE && size >= sizeof(fd_set);
}

void guestFdSet(int fd, fd_set* set, size_t size) {
    if (set && validFdSet(fd, size)) FD_SET(fd, set);
}

int guestFdIsSet(int fd, const fd_set* set, size_t size) {
    return set && validFdSet(fd, size) && FD_ISSET(fd, set) ? 1 : 0;
}

void guestFdClear(int fd, fd_set* set, size_t size) {
    if (set && validFdSet(fd, size)) FD_CLR(fd, set);
}

int guestSelect(int count, fd_set* readSet, fd_set* writeSet, fd_set* exceptionSet, AndroidTimeval* timeout) {
    timeval native{};
    if (timeout) {
        if (timeout->seconds < 0 || timeout->microseconds < 0 || timeout->microseconds >= 1000000)
            return fail(EINVAL);
        native.tv_sec = timeout->seconds;
        native.tv_usec = static_cast<suseconds_t>(timeout->microseconds);
    }
    if (count < 0 || count > FD_SETSIZE) return fail(EINVAL);
    // Both ARM64 ABIs store 1024 descriptor bits in the same little-endian order.
    const int result = select(count, readSet, writeSet, exceptionSet, timeout ? &native : nullptr);
    return result < 0 ? fail(errno) : result;
}

int guestPoll(pollfd* descriptors, unsigned long count, int timeout) {
    // The layout and the six base readiness bits are identical. CDK uses select, so
    // do not advertise support for Linux's additional band/half-close events.
    constexpr int supported = POLLIN | POLLPRI | POLLOUT | POLLERR | POLLHUP | POLLNVAL;
    if (count > FD_SETSIZE || (count && !descriptors)) return fail(EINVAL);
    for (unsigned long i = 0; i < count; ++i) if (descriptors[i].events & ~supported) return fail(EINVAL);
    const int result = poll(descriptors, static_cast<nfds_t>(count), timeout);
    return result < 0 ? fail(errno) : result;
}

}

uint64_t aciesResolveGatewayImport(const char* name) {
    if (!configuredEndpoint().host) return 0;
    if (!strcmp(name, "getaddrinfo")) return reinterpret_cast<uint64_t>(&guestGetAddrInfo);
    if (!strcmp(name, "freeaddrinfo")) return reinterpret_cast<uint64_t>(&guestFreeAddrInfo);
    if (!strcmp(name, "socket")) return reinterpret_cast<uint64_t>(&guestSocket);
    if (!strcmp(name, "connect")) return reinterpret_cast<uint64_t>(&guestConnect);
    if (!strcmp(name, "fcntl")) return reinterpret_cast<uint64_t>(&guestFcntl);
    if (!strcmp(name, "setsockopt")) return reinterpret_cast<uint64_t>(&guestSetSockOpt);
    if (!strcmp(name, "getsockopt")) return reinterpret_cast<uint64_t>(&guestGetSockOpt);
    if (!strcmp(name, "send")) return reinterpret_cast<uint64_t>(&guestSend);
    if (!strcmp(name, "recv")) return reinterpret_cast<uint64_t>(&guestReceive);
    if (!strcmp(name, "__FD_SET_chk")) return reinterpret_cast<uint64_t>(&guestFdSet);
    if (!strcmp(name, "__FD_ISSET_chk")) return reinterpret_cast<uint64_t>(&guestFdIsSet);
    if (!strcmp(name, "__FD_CLR_chk")) return reinterpret_cast<uint64_t>(&guestFdClear);
    if (!strcmp(name, "select")) return reinterpret_cast<uint64_t>(&guestSelect);
    if (!strcmp(name, "poll")) return reinterpret_cast<uint64_t>(&guestPoll);
    return 0;
}
