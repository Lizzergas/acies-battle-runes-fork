#include "offline-imports.h"

#include <cerrno>
#include <cstring>

namespace {
int denied() {
    errno = EACCES;
    return -1;
}

int deniedDNS() {
    // Android netdb.h uses the same EAI_FAIL value as Darwin.
    return 4;
}
}

uint64_t aciesResolveOfflineImport(const char* name) {
    if (std::strcmp(name, "socket") == 0 || std::strcmp(name, "connect") == 0 ||
        std::strcmp(name, "sendto") == 0 || std::strcmp(name, "sendmsg") == 0 ||
        std::strcmp(name, "send") == 0) return reinterpret_cast<uint64_t>(&denied);
    if (std::strcmp(name, "getaddrinfo") == 0) return reinterpret_cast<uint64_t>(&deniedDNS);
    return 0;
}
