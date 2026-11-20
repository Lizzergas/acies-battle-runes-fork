#include "crypto-bridge.h"

#include <CommonCrypto/CommonCryptor.h>
#include <CommonCrypto/CommonDigest.h>

#include <array>
#include <climits>
#include <cstdint>
#include <cstring>
#include <memory>
#include <optional>
#include <unordered_map>
#include <vector>

#include "arm64_context.h"
#include "jni_env.h"
#include "shim.h"

namespace {

using Bytes = std::vector<uint8_t>;

enum Token : size_t { crypto_class, encrypt, decrypt, sha1, none };
std::array<char, none> tokens{};
std::array<ArcCtxFn, 256> previous{};
thread_local Token pending = none;
thread_local std::unordered_map<uint64_t, std::unique_ptr<Bytes>> byte_arrays;

constexpr unsigned find_class = 6;
constexpr unsigned new_global_ref = 21;
constexpr unsigned delete_global_ref = 22;
constexpr unsigned delete_local_ref = 23;
constexpr unsigned get_static_method_id = 113;
constexpr unsigned call_static_object_v = 115;
constexpr unsigned array_length = 171;
constexpr unsigned new_byte_array = 176;
constexpr unsigned get_byte_array_region = 200;
constexpr unsigned set_byte_array_region = 208;

uint64_t token(Token type) { return reinterpret_cast<uint64_t>(&tokens[type]); }

bool matches(const char* actual, const char* expected) {
    return actual && std::strcmp(actual, expected) == 0;
}

Bytes* bytesAt(uint64_t address) {
    auto it = byte_arrays.find(address);
    return it == byte_arrays.end() ? nullptr : it->second.get();
}

uint64_t makeBytes(Bytes bytes) {
    auto object = std::make_unique<Bytes>(std::move(bytes));
    const auto handle = reinterpret_cast<uint64_t>(object.get());
    byte_arrays.emplace(handle, std::move(object));
    return handle;
}

const uint8_t* inputAddress(const Bytes& bytes) {
    static const uint8_t empty = 0;
    return bytes.empty() ? &empty : bytes.data();
}

void clearKey(Bytes& key) {
    volatile uint8_t* bytes = key.data();
    for (size_t i = 0; i < key.size(); ++i) bytes[i] = 0;
}

std::optional<Bytes> cipher(Token operation, const Bytes& input, Bytes& key) {
    constexpr size_t block_size = kCCBlockSizeAES128;
    const bool valid_key = key.size() == kCCKeySizeAES128 || key.size() == kCCKeySizeAES192 ||
                           key.size() == kCCKeySizeAES256;
    if (!valid_key) {
        clearKey(key);
        return std::nullopt;
    }
    const bool encrypting = operation == encrypt;
    Bytes output(input.size() + block_size);
    size_t written = 0;
    const auto status = CCCrypt(encrypting ? kCCEncrypt : kCCDecrypt,
        kCCAlgorithmAES, encrypting ? kCCOptionPKCS7Padding : 0, key.data(), key.size(), key.data(),
        inputAddress(input), input.size(), output.data(), output.size(), &written);
    clearKey(key);
    if (status != kCCSuccess) return std::nullopt;
    if (!encrypting && written) {
        if (written < block_size) return std::nullopt;
        // Apple's CBC padding path may accept a zero-length last block pad.
        // The Android Java Cipher contract rejects zero and all malformed padding.
        const unsigned padding = output[written - 1];
        unsigned mismatch = padding == 0 || padding > block_size;
        for (unsigned offset = 0; offset < block_size; ++offset) {
            const unsigned mask = 0u - unsigned(offset < padding);
            mismatch |= mask & (padding ^ output[written - 1 - offset]);
        }
        if (mismatch) return std::nullopt;
        written -= padding;
    }
    output.resize(written);
    return output;
}

Bytes digest(const Bytes& input) {
    Bytes result(CC_SHA1_DIGEST_LENGTH);
    CC_SHA1(inputAddress(input), static_cast<CC_LONG>(input.size()), result.data());
    return result;
}

Token method(const char* name, const char* signature) {
    if (matches(signature, "([B[B)[B")) {
        if (matches(name, "encrypt")) return encrypt;
        if (matches(name, "decrypt")) return decrypt;
    }
    if (matches(signature, "([B)[B") && matches(name, "sha1")) return sha1;
    return none;
}

template <unsigned Slot>
bool handle(Arm64Ctx* ctx) {
    if constexpr (Slot == find_class) {
        if (!matches(reinterpret_cast<const char*>(ctx->x[1]), "kr/co/brgames/cdk/CSCrypto")) {
            return false;
        }
        ctx->x[0] = token(crypto_class);
    } else if constexpr (Slot == new_global_ref) {
        if (ctx->x[1] != token(crypto_class)) return false;
        ctx->x[0] = ctx->x[1];
    } else if constexpr (Slot == delete_local_ref || Slot == delete_global_ref) {
        if (ctx->x[1] != token(crypto_class) && !byte_arrays.erase(ctx->x[1])) return false;
        ctx->x[0] = 0;
    } else if constexpr (Slot == get_static_method_id) {
        if (ctx->x[1] != token(crypto_class)) return false;
        pending = method(reinterpret_cast<const char*>(ctx->x[2]),
                         reinterpret_cast<const char*>(ctx->x[3]));
        ctx->x[0] = pending == none ? 0 : token(pending);
    } else if constexpr (Slot == new_byte_array) {
        if (pending == none) return false;
        const auto size = static_cast<uint32_t>(ctx->x[1]);
        ctx->x[0] = size <= INT_MAX ? makeBytes(Bytes(size)) : 0;
    } else if constexpr (Slot == get_byte_array_region || Slot == set_byte_array_region) {
        auto* bytes = bytesAt(ctx->x[1]);
        if (!bytes) return false;
        const auto offset = static_cast<uint32_t>(ctx->x[2]);
        const auto count = static_cast<uint32_t>(ctx->x[3]);
        auto* address = reinterpret_cast<void*>(ctx->x[4]);
        if (address && count && offset <= bytes->size() && count <= bytes->size() - offset) {
            if constexpr (Slot == get_byte_array_region) {
                std::memcpy(address, bytes->data() + offset, count);
            } else {
                std::memcpy(bytes->data() + offset, address, count);
            }
        }
        ctx->x[0] = 0;
    } else if constexpr (Slot == array_length) {
        auto* bytes = bytesAt(ctx->x[1]);
        if (!bytes) return false;
        ctx->x[0] = bytes->size();
    } else if constexpr (Slot == call_static_object_v) {
        if (ctx->x[1] != token(crypto_class) || pending == none) return false;
        const auto operation = pending;
        pending = none;
        const auto method_id = ctx->x[2];
        const auto arguments = ctx->x[3];
        ctx->x[0] = 0;
        if (!arguments || method_id != token(operation)) return true;
        Bytes cursor(arc::ShimVaListSize());
        std::memcpy(cursor.data(), reinterpret_cast<const void*>(arguments), cursor.size());
        const auto* input = bytesAt(arc::ShimVaNextInt(cursor.data()));
        if (operation == sha1) {
            if (input) ctx->x[0] = makeBytes(digest(*input));
        } else if (auto* key = bytesAt(arc::ShimVaNextInt(cursor.data()))) {
            if (input) {
                auto output = cipher(operation, *input, *key);
                if (output) ctx->x[0] = makeBytes(std::move(*output));
            } else clearKey(*key);
        }
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

extern "C" void acies_aot_install_crypto_jni(void) {
    install<find_class>("FindClass.crypto");
    install<new_global_ref>("NewGlobalRef.crypto");
    install<delete_global_ref>("DeleteGlobalRef.crypto");
    install<delete_local_ref>("DeleteLocalRef.crypto");
    install<get_static_method_id>("GetStaticMethodID.crypto");
    install<call_static_object_v>("CallStaticObjectMethodV.crypto");
    install<array_length>("GetArrayLength.crypto");
    install<new_byte_array>("NewByteArray.crypto");
    install<get_byte_array_region>("GetByteArrayRegion.crypto");
    install<set_byte_array_region>("SetByteArrayRegion.crypto");
}
