#include <cstdio>
#include <cstring>

extern "C" int acies_aot_asset_probe(const char*, const char*, const char*, const char*, char*, size_t);
extern "C" int acies_aot_icu_probe(const char*, const char*, char*, size_t);
extern "C" int acies_aot_native_start_probe(const char*, const char*, const char*, const char*, char*, size_t);

int main(int argc, char** argv) {
    if (argc != 6) return 2;
    char report[1024]{};
    int code;
    if (std::strcmp(argv[1], "asset") == 0) {
        code = acies_aot_asset_probe(argv[2], argv[3], argv[4], argv[5], report, sizeof(report));
    } else if (std::strcmp(argv[1], "icu") == 0) {
        code = acies_aot_icu_probe(argv[2], argv[3], report, sizeof(report));
    } else if (std::strcmp(argv[1], "start") == 0) {
        code = acies_aot_native_start_probe(argv[2], argv[3], argv[4], argv[5], report, sizeof(report));
    } else {
        return 2;
    }
    std::puts(report);
    return code;
}
