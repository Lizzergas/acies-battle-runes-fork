#pragma once

#include <cstdint>
#include <string>

struct LocalAdmissionReply {
    uint64_t target = 0;
    int status = 0;
    std::string body;
};

void aciesInstallLocalAdmissionJNI();
bool aciesTakeLocalAdmissionReply(LocalAdmissionReply& reply);
bool aciesLocalReplyStillActive(uint64_t target);
uint64_t aciesSetLocalAdmissionByteArray(const std::string* body);
