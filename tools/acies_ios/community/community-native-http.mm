#import "community-auth.h"
#include "community-native-http.h"

#include <cctype>
#include <strings.h>
#include <mutex>
#include <string_view>

@interface AciesCommunityNativeRedirects : NSObject <NSURLSessionTaskDelegate>
@end

@implementation AciesCommunityNativeRedirects
- (void)URLSession:(NSURLSession*)session task:(NSURLSessionTask*)task
    willPerformHTTPRedirection:(NSHTTPURLResponse*)response newRequest:(NSURLRequest*)request
    completionHandler:(void (^)(NSURLRequest*))completionHandler {
    (void)session;
    (void)task;
    (void)response;
    (void)request;
    completionHandler(nil);
}
@end

namespace {

constexpr size_t maximum_body = 512 * 1024;
std::mutex context_mutex;
AciesCommunitySession* current_account;
NSURLSession* native_session;
unsigned current_gateway_port;

bool ownedPath(std::string_view path) {
    if (path.size() > 2048 || path.find("..") != std::string_view::npos ||
        path.find("//") != std::string_view::npos) return false;
    if (path.rfind("/api/client/", 0) != 0 && path.rfind("/api/client-secure/", 0) != 0) {
        return false;
    }
    for (const unsigned char ch : path) {
        if (!std::isalnum(ch) && std::string_view("/._-?=&%").find(ch) == std::string_view::npos) {
            return false;
        }
    }
    return true;
}

bool forwardedHeader(const std::string& name, const std::string& value) {
    if (name.empty() || name.size() > 80 || value.size() > 8192) return false;
    for (const unsigned char ch : name) if (!std::isalnum(ch) && ch != '-') return false;
    for (const unsigned char ch : value) if (ch < 32 || ch == 127) return false;
    for (const char* reserved : {"Authorization", "X-Acies-Gateway-Port", "Cookie", "Host",
                                 "Connection", "Content-Length", "Transfer-Encoding", "Proxy-Authorization"}) {
        if (strcasecmp(name.c_str(), reserved) == 0) return false;
    }
    return true;
}

} // namespace

bool acies_aot_bind_community_native_http(AciesCommunitySession* session, unsigned gateway_port) {
    if (!session.origin || !session.bearer.length || (gateway_port && gateway_port < 1024) || gateway_port > 65535) {
        return false;
    }
    std::lock_guard lock(context_mutex);
    if (!native_session) {
        NSURLSessionConfiguration* configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
        configuration.timeoutIntervalForRequest = 8;
        configuration.timeoutIntervalForResource = 8;
        configuration.HTTPShouldSetCookies = NO;
        configuration.URLCache = nil;
        configuration.URLCredentialStorage = nil;
        native_session = [NSURLSession sessionWithConfiguration:configuration
            delegate:[AciesCommunityNativeRedirects new] delegateQueue:nil];
    }
    current_account = session;
    current_gateway_port = gateway_port;
    return YES;
}

bool acies_aot_has_community_native_http() {
    std::lock_guard lock(context_mutex);
    return current_account != nil;
}

std::string acies_aot_community_owned_path(const std::string& original_url) {
    if (original_url.size() > 4096) return {};
    @autoreleasepool {
        NSURL* activeOrigin;
        {
            std::lock_guard lock(context_mutex);
            activeOrigin = current_account.origin;
        }
        if (!activeOrigin) return {};
        NSString* text = [NSString stringWithUTF8String:original_url.c_str()];
        NSURLComponents* url = text ? [NSURLComponents componentsWithString:text] : nil;
        if (!url.host || url.user || url.password || url.fragment) return {};
        NSString* scheme = url.scheme.lowercaseString;
        if (![scheme isEqualToString:@"https"] && ![scheme isEqualToString:@"http"]) return {};
        auto port = [](NSString* scheme, NSNumber* explicitPort) {
            return explicitPort ? explicitPort.integerValue : ([scheme isEqualToString:@"https"] ? 443 : 80);
        };
        NSString* activeScheme = activeOrigin.scheme.lowercaseString;
        NSString* host = url.host.lowercaseString;
        const bool sameScheme = [scheme isEqualToString:activeScheme] ||
            ([host isEqualToString:@"127.0.0.1"] && [activeScheme isEqualToString:@"http"] &&
             [scheme isEqualToString:@"https"]);
        const bool configured = [host isEqualToString:activeOrigin.host.lowercaseString] &&
            sameScheme && port(scheme, url.port) == port(activeScheme, activeOrigin.port);
        const bool closed = ([host isEqualToString:@"live.saintjoy.co.kr"] ||
                             [host isEqualToString:@"col-glob-lb01.srv.creagames.com"]) &&
            (!url.port || port(scheme, url.port) == port(scheme, nil));
        if (!configured && !closed) return {};
        NSString* raw = url.percentEncodedPath ?: @"";
        if (url.percentEncodedQuery.length) raw = [raw stringByAppendingFormat:@"?%@", url.percentEncodedQuery];
        const char* result = raw.UTF8String;
        return result && ownedPath(result) ? std::string(result) : std::string();
    }
}

AciesCommunityNativeReply acies_aot_community_native_http(
    const std::string& path, const std::string& method,
    const std::map<std::string, std::string>& headers, const std::string& body) {
    if (!ownedPath(path) || (method != "GET" && method != "POST") ||
        body.size() > maximum_body || NSThread.isMainThread) return {};

    @autoreleasepool {
        AciesCommunitySession* account;
        NSURLSession* client;
        unsigned gateway_port;
        {
            std::lock_guard lock(context_mutex);
            account = current_account;
            client = native_session;
            gateway_port = current_gateway_port;
        }
        if (!account || !client) return {};
        NSURL* url = [[NSURL URLWithString:[NSString stringWithUTF8String:path.c_str()]
                             relativeToURL:account.origin] absoluteURL];
        if (!url || ![url.host isEqualToString:account.origin.host] ||
            ![url.scheme isEqualToString:account.origin.scheme] ||
            ((url.port || account.origin.port) && ![url.port isEqual:account.origin.port])) return {};
        const char* decoded_path = url.path.UTF8String;
        if (!decoded_path || !ownedPath(decoded_path)) return {};

        auto request = [NSMutableURLRequest requestWithURL:url];
        request.HTTPMethod = [NSString stringWithUTF8String:method.c_str()];
        if (!body.empty()) request.HTTPBody = [NSData dataWithBytes:body.data() length:body.size()];
        for (const auto& [name, value] : headers) {
            if (!forwardedHeader(name, value)) continue;
            NSString* fieldValue = [NSString stringWithUTF8String:value.c_str()];
            if (fieldValue) {
                [request setValue:fieldValue forHTTPHeaderField:[NSString stringWithUTF8String:name.c_str()]];
            }
        }
        [request setValue:[@"Bearer " stringByAppendingString:account.bearer] forHTTPHeaderField:@"Authorization"];
        if (gateway_port) {
            [request setValue:[NSString stringWithFormat:@"%u", gateway_port] forHTTPHeaderField:@"X-Acies-Gateway-Port"];
        }

        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        __block NSData* received = nil;
        __block int status = 0;
        auto task = [client dataTaskWithRequest:request completionHandler:
            ^(NSData* data, NSURLResponse* response, NSError* error) {
                if (!error && [response isKindOfClass:NSHTTPURLResponse.class] && data.length <= maximum_body) {
                    const auto value = ((NSHTTPURLResponse*)response).statusCode;
                    if (value >= 200 && value <= 599 && (value < 300 || value >= 400)) {
                        status = int(value);
                        received = data;
                    }
                }
                dispatch_semaphore_signal(done);
            }];
        [task resume];
        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 9 * NSEC_PER_SEC))) {
            [task cancel];
            return {};
        }
        std::string bytes;
        if (received.length) bytes.assign(static_cast<const char*>(received.bytes), received.length);
        return {status, std::move(bytes)};
    }
}
