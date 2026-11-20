#include "community-gateway-mode.h"

#include <atomic>
#include <cstring>

namespace {
std::atomic<bool> enabled{false};

uint64_t guestPointer(uint64_t address) {
    uint64_t value = 0;
    std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof value);
    return value;
}
}

extern "C" void acies_aot_use_community_gateway(bool community) {
    enabled.store(community);
}

extern "C" uint64_t acies_aot_community_gateway_secret(uint64_t image_base, uint64_t legacy_locale) {
    if (!enabled.load() || !image_base) return legacy_locale;
    // Same fields the Android community build uses in its tagged 2.5.1 binary.
    constexpr uint64_t lobby_gateway_global = 0x8eea48;
    constexpr uint64_t gateway_session_field = 0x40;
    constexpr uint64_t session_secret_field = 0x20;
    const auto gateway = guestPointer(image_base + lobby_gateway_global);
    const auto session = gateway ? guestPointer(gateway + gateway_session_field) : 0;
    return session ? guestPointer(session + session_secret_field) : 0;
}
