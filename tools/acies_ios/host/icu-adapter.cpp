#include "icu-adapter.h"

#include <cerrno>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <mutex>
#include <set>
#include <string>

#include "arm64_context.h"
#include "shim.h"

namespace {
struct AndroidDirectoryEntry {
    uint64_t inode;
    int64_t offset;
    uint16_t recordLength;
    uint8_t type;
    char name[256];
};
static_assert(offsetof(AndroidDirectoryEntry, name) == 19, "Android dirent64 layout");

void* icuLibrary = nullptr;
uint8_t icuVersion[4]{};
std::string icuSuffix;
std::mutex symbolsMutex;
std::set<std::string> stableNames;

int scanICU(const char* path, AndroidDirectoryEntry*** results, uint64_t filter, uint64_t) {
    if (std::strcmp(path, "/system/usr/icu") != 0 || !icuLibrary) {
        errno = ENOENT;
        return -1;
    }

    *results = nullptr;
    AndroidDirectoryEntry entry{};
    entry.inode = 1;
    entry.recordLength = sizeof(entry);
    entry.type = 8; // Linux DT_REG
    std::snprintf(entry.name, sizeof(entry.name), "icudt%ul.dat", unsigned(icuVersion[0]));
    const uint64_t filterArgs[] = {reinterpret_cast<uint64_t>(&entry)};
    if (filter && !arc_call_guest(filter, filterArgs, 1)) return 0;

    auto* result = static_cast<AndroidDirectoryEntry**>(std::malloc(sizeof(*results)));
    auto* record = static_cast<AndroidDirectoryEntry*>(std::malloc(sizeof(entry)));
    if (!result || !record) {
        std::free(result);
        std::free(record);
        errno = ENOMEM;
        return -1;
    }
    *record = entry;
    *result = record;
    *results = result;
    return 1;
}

void* openICU(const char* name, int flags) {
    if (name && (std::strcmp(name, "libicuuc.so") == 0 ||
                 std::strcmp(name, "libicui18n.so") == 0)) return icuLibrary;
    auto next = reinterpret_cast<void* (*)(const char*, int)>(arc::ShimResolve("dlopen"));
    return next ? next(name, flags) : nullptr;
}

void* findICU(void* handle, const char* name) {
    if (icuLibrary && handle == icuLibrary) {
        // Android includes the data version in its symbol lookup. Darwin's ICU
        // exposes the same C entry points without the Android version suffix.
        const std::string query(name);
        if (query.size() <= icuSuffix.size() ||
            query.compare(query.size() - icuSuffix.size(), icuSuffix.size(), icuSuffix) != 0) {
            return nullptr;
        }
        const std::string platformName = query.substr(0, query.size() - icuSuffix.size());
        auto* address = ::dlsym(icuLibrary, platformName.c_str());
        if (address) {
            const std::lock_guard<std::mutex> lock(symbolsMutex);
            const auto& stableName = *stableNames.insert(query).first;
            arc_register_native(reinterpret_cast<uint64_t>(address), stableName.c_str());
        }
        return address;
    }

    auto next = reinterpret_cast<void* (*)(void*, const char*)>(arc::ShimResolve("dlsym"));
    return next ? next(handle, name) : nullptr;
}

int compareICUEntries(const AndroidDirectoryEntry** a, const AndroidDirectoryEntry** b) {
    return std::strcoll((*a)->name, (*b)->name);
}
}

bool aciesConfigureICU() {
    icuLibrary = ::dlopen("/usr/lib/libicucore.A.dylib", RTLD_LAZY | RTLD_LOCAL);
    if (!icuLibrary) return false;

    auto version = reinterpret_cast<void (*)(uint8_t*)>(::dlsym(icuLibrary, "u_getVersion"));
    if (!version) return false;
    version(icuVersion);
    icuSuffix = "_" + std::to_string(icuVersion[0]);
    return icuVersion[0] != 0;
}

uint64_t aciesResolveICUImport(const char* name) {
    if (std::strcmp(name, "scandir") == 0) return reinterpret_cast<uint64_t>(&scanICU);
    if (std::strcmp(name, "alphasort") == 0) return reinterpret_cast<uint64_t>(&compareICUEntries);
    if (std::strcmp(name, "dlopen") == 0) return reinterpret_cast<uint64_t>(&openICU);
    if (std::strcmp(name, "dlsym") == 0) return reinterpret_cast<uint64_t>(&findICU);
    return 0;
}
