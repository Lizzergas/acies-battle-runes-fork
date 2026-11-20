#pragma once

#include <map>
#include <string>

struct AciesCommunityNativeReply {
    int status = 0;
    std::string body;
};

#ifdef __OBJC__
@class AciesCommunitySession;
bool acies_aot_bind_community_native_http(AciesCommunitySession* session, unsigned gateway_port);
#endif

bool acies_aot_has_community_native_http();
std::string acies_aot_community_owned_path(const std::string& original_url);
AciesCommunityNativeReply acies_aot_community_native_http(
    const std::string& path, const std::string& method,
    const std::map<std::string, std::string>& headers, const std::string& body);
