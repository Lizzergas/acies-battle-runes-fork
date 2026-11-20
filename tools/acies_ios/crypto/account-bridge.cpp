#include "account-bridge.h"

#include <CoreFoundation/CoreFoundation.h>
#include <uuid/uuid.h>

#include <array>
#include <cstdint>
#include <cstring>
#include <deque>
#include <mutex>

#include "arm64_context.h"
#include "jni_env.h"

namespace {

enum Token : size_t {
    device_class,
    billing_class,
    play_class,
    device_uuid,
    device_country,
    billing_connect,
    billing_sync,
    play_login,
    count
};

struct Event {
    const char* callback;
    int32_t argument;
};

constexpr Event billing_unavailable{
    "Java_kr_co_brgames_cdk_extension_CSGoogleIAP_nativeError", 3
};
constexpr Event google_play_unavailable{
    "Java_kr_co_brgames_cdk_extension_CSGooglePlay_nativeLoginResult", 2
};

std::array<char, count> tokens{};
std::array<ArcCtxFn, 256> previous{};
bool provider_events_enabled = false;
std::mutex event_mutex;
std::deque<Event> events;

constexpr unsigned find_class = 6;
constexpr unsigned new_global_ref = 21;
constexpr unsigned delete_global_ref = 22;
constexpr unsigned delete_local_ref = 23;
constexpr unsigned get_static_method_id = 113;
constexpr unsigned call_static_object_v = 115;
constexpr unsigned call_static_void_v = 142;

uint64_t token(Token kind) { return reinterpret_cast<uint64_t>(&tokens[kind]); }

bool matches(const char* actual, const char* expected) {
    return actual && std::strcmp(actual, expected) == 0;
}

bool classHandle(uint64_t handle) {
    return handle == token(device_class) || handle == token(billing_class) ||
           handle == token(play_class);
}

uint64_t newDeviceUUID() {
    uuid_t bytes;
    char text[37];
    uuid_generate_random(bytes);
    uuid_unparse_lower(bytes, text);
    return arc_jni_string(text);
}

uint64_t localCountryCode() {
    char text[16] = {};
    CFLocaleRef locale = CFLocaleCopyCurrent();
    if (locale) {
        auto country = static_cast<CFStringRef>(CFLocaleGetValue(locale, kCFLocaleCountryCode));
        if (country && !CFStringGetCString(country, text, sizeof text, kCFStringEncodingUTF8)) {
            text[0] = '\0';
        }
        CFRelease(locale);
    }
    return arc_jni_string(text);
}

template <unsigned Slot>
bool handle(Arm64Ctx* ctx) {
    if constexpr (Slot == find_class) {
        const char* name = reinterpret_cast<const char*>(ctx->x[1]);
        if (matches(name, "kr/co/brgames/cdk/CSDevice")) ctx->x[0] = token(device_class);
        else if (provider_events_enabled && matches(name, "kr/co/brgames/cdk/extension/CSGoogleIAP")) ctx->x[0] = token(billing_class);
        else if (provider_events_enabled && matches(name, "kr/co/brgames/cdk/extension/CSGooglePlay")) ctx->x[0] = token(play_class);
        else return false;
    } else if constexpr (Slot == new_global_ref || Slot == delete_local_ref || Slot == delete_global_ref) {
        if (!classHandle(ctx->x[1])) return false;
        ctx->x[0] = Slot == new_global_ref ? ctx->x[1] : 0;
    } else if constexpr (Slot == get_static_method_id) {
        const uint64_t clazz = ctx->x[1];
        const char* name = reinterpret_cast<const char*>(ctx->x[2]);
        const char* signature = reinterpret_cast<const char*>(ctx->x[3]);
        if (clazz == token(device_class) && matches(signature, "()Ljava/lang/String;")) {
            if (matches(name, "uuid")) ctx->x[0] = token(device_uuid);
            else if (matches(name, "countryCode")) ctx->x[0] = token(device_country);
            else return false;
        } else if (clazz == token(billing_class)) {
            if (matches(name, "connect") && matches(signature, "()V")) {
                ctx->x[0] = token(billing_connect);
            } else if (matches(name, "sync") && matches(signature, "([Ljava/lang/String;)V")) {
                ctx->x[0] = token(billing_sync);
            } else return false;
        } else if (clazz == token(play_class) && matches(name, "login") && matches(signature, "()V")) {
            ctx->x[0] = token(play_login);
        } else return false;
    } else if constexpr (Slot == call_static_object_v) {
        if (ctx->x[1] != token(device_class)) return false;
        if (ctx->x[2] == token(device_uuid)) ctx->x[0] = newDeviceUUID();
        else if (ctx->x[2] == token(device_country)) ctx->x[0] = localCountryCode();
        else return false;
    } else if constexpr (Slot == call_static_void_v) {
        const uint64_t clazz = ctx->x[1];
        const uint64_t method = ctx->x[2];
        Event event{};
        if (clazz == token(billing_class) && (method == token(billing_connect) || method == token(billing_sync))) {
            event = billing_unavailable;
        } else if (clazz == token(play_class) && method == token(play_login)) {
            event = google_play_unavailable;
        } else return false;
        {
            std::lock_guard lock(event_mutex);
            events.push_back(event);
        }
        ctx->x[0] = 0;
    }
    return true;
}

template <unsigned Slot>
void dispatch(Arm64Ctx* ctx) {
    if (!handle<Slot>(ctx)) previous[Slot](ctx);
}

template <unsigned Slot>
void install(const char* name) {
    if (previous[Slot]) return;
    auto* table = reinterpret_cast<uint64_t*>(*reinterpret_cast<const uint64_t*>(arc_jni_env()));
    previous[Slot] = reinterpret_cast<ArcCtxFn>(table[Slot]);
    table[Slot] = reinterpret_cast<uint64_t>(&dispatch<Slot>);
    arc_register_ctx_native(table[Slot], name, &dispatch<Slot>);
}

} // namespace

extern "C" void acies_aot_install_device_info_jni(void) {
    install<find_class>("FindClass.account");
    install<new_global_ref>("NewGlobalRef.account");
    install<delete_global_ref>("DeleteGlobalRef.account");
    install<delete_local_ref>("DeleteLocalRef.account");
    install<get_static_method_id>("GetStaticMethodID.account");
    install<call_static_object_v>("CallStaticObjectMethodV.account");
}

extern "C" void acies_aot_install_account_jni(void) {
    provider_events_enabled = true;
    acies_aot_install_device_info_jni();
    install<call_static_void_v>("CallStaticVoidMethodV.account");
}

extern "C" bool acies_aot_take_account_event(const char** callback, int32_t* argument) {
    if (!callback || !argument) return false;
    std::lock_guard lock(event_mutex);
    if (events.empty()) return false;
    const Event event = events.front();
    events.pop_front();
    *callback = event.callback;
    *argument = event.argument;
    return true;
}
