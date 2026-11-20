#import "community-auth.h"

#include <cstdio>
#if defined(ACIES_WITH_GAME)
#include <cstdlib>
#include <future>
#import <CommonCrypto/CommonCryptor.h>
#include "community-native-http.h"
extern "C" int acies_aot_native_start_probe(const char*, const char*, const char*, const char*, char*, size_t);
#endif

typedef void (^Begin)(AciesCommunityResult);
AciesCommunitySession* doRequest(Begin begin) {
    auto done = dispatch_semaphore_create(0);
    __block AciesCommunitySession* result = nil;
    begin(^(AciesCommunitySession* session, NSError* error) {
        if (error) std::fprintf(stderr, "Local community account request failed (code %ld).\n", long(error.code));
        result = session;
        dispatch_semaphore_signal(done);
    });
    if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 15 * NSEC_PER_SEC))) {
        return nil;
    }
    return result;
}

int main(int argc, char** argv) {
    @autoreleasepool {
        if (argc != 3) return 2;
        NSString* origin = [NSString stringWithUTF8String:argv[1]];
        NSURL* storage = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[2]] isDirectory:YES];
        AciesCommunityClient* client = [[AciesCommunityClient alloc] initWithOrigin:[NSURL URLWithString:origin] allowLoopbackHTTP:YES];
        if (!client) return 1;
        NSString* password = NSUUID.UUID.UUIDString;
        NSString* username = @"fixture_account";
        auto registered = doRequest(^(AciesCommunityResult result) {
            [client registerUser:username password:password invite:@"" completion:result];
        });
        if (!registered) return 1;
        auto signedIn = doRequest(^(AciesCommunityResult result) {
            [client signIn:username password:password completion:result];
        });
        if (!signedIn) return 1;
        auto verified = doRequest(^(AciesCommunityResult result) {
            [client resume:signedIn.bearer completion:result];
        });
        if (!verified) return 1;
        NSError* error = nil;
        if (registered.userID != signedIn.userID || signedIn.userID != verified.userID ||
            [registered.bearer isEqual:signedIn.bearer] ||
            ![signedIn.gatewaySecret isEqual:verified.gatewaySecret] ||
            ![verified prepareNativeStorage:storage error:&error]) {
            std::fprintf(stderr, "Community identity or native session storage did not match.\n");
            return 1;
        }

        std::fprintf(stderr, "ACIES COMMUNITY ACCOUNT PASS: registration, sign-in, validated session, native SessionInfo file.\n");
#if defined(ACIES_WITH_GAME)
        if (!acies_aot_bind_community_native_http(verified, 0) ||
            !acies_aot_community_owned_path("https://unrelated.invalid/api/client/login").empty() ||
            !acies_aot_community_owned_path("https://live.saintjoy.co.kr/other").empty()) return 1;
        auto askForGateway = [] {
            return std::async(std::launch::async, [] {
                return acies_aot_community_native_http("/api/client-secure/pvp-server", "POST", {}, {});
            }).get();
        };
        if (askForGateway().status != 400 || !acies_aot_bind_community_native_http(verified, 48138)) return 1;
        const auto secure = askForGateway();
        const char* fixture_key = "localmockkey0001";
        uint8_t clear[256]{};
        size_t length = 0;
        if (secure.status != 200 ||
            CCCrypt(kCCDecrypt, kCCAlgorithmAES, kCCOptionPKCS7Padding, fixture_key, 16, fixture_key,
                secure.body.data(), secure.body.size(), clear, sizeof clear, &length) != kCCSuccess) return 1;
        NSData* response = [NSData dataWithBytes:clear length:length];
        NSDictionary* gateway = [NSJSONSerialization JSONObjectWithData:response options:0 error:nil];
        if (![gateway[@"host"] isEqual:@"127.0.0.1"] || ![gateway[@"port"] isEqual:@48138]) return 1;
        std::fprintf(stderr, "ACIES COMMUNITY HTTP PASS: authorization, origin restriction, gateway absent and binary response cases.\n");
        NSURL* acceptedTerms = [storage URLByAppendingPathComponent:@"agreeTerms.xmf"];
        // The disposable fixture models prior acceptance in this otherwise fresh storage.
        if (![[NSData data] writeToURL:acceptedTerms options:NSDataWritingAtomic error:&error]) return 1;
        char report[1024]{};
        const int status = acies_aot_native_start_probe(std::getenv("ACIES_COMMUNITY_ENGINE"),
            std::getenv("ACIES_COMMUNITY_CXX"), std::getenv("ACIES_COMMUNITY_ASSETS"),
            storage.fileSystemRepresentation, report, sizeof report);
        std::fprintf(stderr, "%s\n", report);
        return status;
#else
        return 0;
#endif
    }
}
