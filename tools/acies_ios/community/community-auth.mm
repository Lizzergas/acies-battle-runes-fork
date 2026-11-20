#import "community-auth.h"

#import <TargetConditionals.h>

#include <cstdint>
#include <cstdio>

namespace {

NSString* errorDomain = @"AciesCommunity";

NSError* accountError(NSInteger status, NSString* message) {
    return [NSError errorWithDomain:errorDomain code:status
                           userInfo:@{NSLocalizedDescriptionKey: message}];
}

bool credential(NSString* value, NSString* prefix) {
    if (![value isKindOfClass:NSString.class] || value.length != 47 || ![value hasPrefix:prefix]) return false;
    for (NSUInteger i = 4; i < value.length; ++i) {
        const unichar ch = [value characterAtIndex:i];
        if (!(('A' <= ch && ch <= 'Z') || ('a' <= ch && ch <= 'z') ||
              ('0' <= ch && ch <= '9') || ch == '-' || ch == '_')) return false;
    }
    return true;
}

bool validOrigin(NSURL* url, BOOL allowLoopbackHTTP) {
    if (!url || !url.host.length || url.user || url.password || url.query || url.fragment ||
        (url.path.length && ![url.path isEqualToString:@"/"]) ||
        (url.port && (url.port.integerValue < 1 || url.port.integerValue > 65535))) {
        return false;
    }
    if ([url.scheme.lowercaseString isEqualToString:@"https"]) return true;
    return allowLoopbackHTTP && [url.scheme.lowercaseString isEqualToString:@"http"] &&
           [url.host isEqualToString:@"127.0.0.1"];
}

NSString* tidy(NSString* input) {
    return [input stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
}

using Reply = void (^)(NSDictionary* _Nullable, NSError* _Nullable);

} // namespace

@interface AciesCommunitySession ()
@property(nonatomic, readwrite, copy) NSURL* origin;
@property(nonatomic, readwrite, copy) NSString* username;
@property(nonatomic, readwrite) int64_t userID;
@property(nonatomic, readwrite, copy) NSString* bearer;
@property(nonatomic, readwrite, copy) NSString* gatewaySecret;
@end

@implementation AciesCommunitySession

- (BOOL)prepareNativeStorage:(NSURL*)storage error:(NSError**)error {
    if (!storage.isFileURL || self.userID <= 0 || !credential(self.gatewaySecret, @"acp_")) {
        if (error) *error = accountError(0, @"Cannot prepare the game's local session.");
        return NO;
    }

    NSFileManager* manager = NSFileManager.defaultManager;
    if (![manager createDirectoryAtURL:storage withIntermediateDirectories:YES
                            attributes:@{NSFilePosixPermissions: @0700} error:error]) return NO;

    const uint64_t user = uint64_t(self.userID);
    uint8_t prefix[9]{};
    for (unsigned i = 0; i < 8; ++i) prefix[i] = uint8_t(user >> (i * 8));
    NSData* secret = [self.gatewaySecret dataUsingEncoding:NSASCIIStringEncoding];
    prefix[8] = uint8_t(secret.length);
    auto data = [NSMutableData dataWithBytes:prefix length:sizeof prefix];
    [data appendData:secret];

    // SessionInfo::createFromLocal uses this key before the transport rewrites the origin.
    NSURL* file = [storage URLByAppendingPathComponent:@"live.saintjoy.co.kr.xmf"];
    NSDataWritingOptions options = NSDataWritingAtomic;
#if TARGET_OS_IPHONE
    options |= NSDataWritingFileProtectionCompleteUntilFirstUserAuthentication;
#endif
    NSURL* staging = [storage URLByAppendingPathComponent:NSUUID.UUID.UUIDString];
    if (![data writeToURL:staging options:options error:error]) return NO;
    BOOL ready = [manager setAttributes:@{NSFilePosixPermissions: @0600} ofItemAtPath:staging.path error:error];
    if (ready && std::rename(staging.fileSystemRepresentation, file.fileSystemRepresentation) == 0) return YES;
    if (ready && error) {
        *error = accountError(0, @"Could not activate the game's local session.");
    }
    [manager removeItemAtURL:staging error:nil];
    return NO;
}

@end

@interface AciesCommunityRedirects : NSObject <NSURLSessionTaskDelegate>
@end

@implementation AciesCommunityRedirects
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

@implementation AciesCommunityClient {
    NSURL* _origin;
    NSURLSession* _transport;
}

- (nullable instancetype)initWithOrigin:(NSURL*)origin allowLoopbackHTTP:(BOOL)allow {
    if (!validOrigin(origin, allow)) return nil;
    self = [super init];
    if (self) {
        _origin = [origin copy];
        NSURLSessionConfiguration* config = NSURLSessionConfiguration.ephemeralSessionConfiguration;
        config.timeoutIntervalForRequest = 8;
        config.timeoutIntervalForResource = 8;
        config.HTTPShouldSetCookies = NO;
        config.URLCache = nil;
        config.URLCredentialStorage = nil;
        _transport = [NSURLSession sessionWithConfiguration:config
                                                  delegate:[AciesCommunityRedirects new] delegateQueue:nil];
    }
    return self;
}

- (void)dealloc {
    [_transport invalidateAndCancel];
}

- (void)request:(NSString*)path method:(NSString*)method bearer:(nullable NSString*)bearer
        payload:(nullable NSDictionary*)payload reply:(Reply)reply {
    NSURL* url = [[NSURL URLWithString:path relativeToURL:_origin] absoluteURL];
    auto request = [NSMutableURLRequest requestWithURL:url];
    request.HTTPMethod = method;
    if (bearer) [request setValue:[@"Bearer " stringByAppendingString:bearer] forHTTPHeaderField:@"Authorization"];
    if (payload) {
        NSError* error = nil;
        request.HTTPBody = [NSJSONSerialization dataWithJSONObject:payload options:0 error:&error];
        if (error) {
            reply(nil, accountError(0, @"Could not prepare the account request."));
            return;
        }
        [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
    }
    [[_transport dataTaskWithRequest:request completionHandler:
        ^(NSData* data, NSURLResponse* response, NSError* error) {
            if (error || ![response isKindOfClass:NSHTTPURLResponse.class]) {
                reply(nil, accountError(0, @"Could not reach the account server."));
                return;
            }
            const NSInteger status = ((NSHTTPURLResponse*)response).statusCode;
            if (data.length > 512 * 1024) {
                reply(nil, accountError(status, @"The account server returned an oversized response."));
                return;
            }
            NSDictionary* json = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
            if (status < 200 || status >= 300) {
                NSString* text = @"The account server could not complete the request.";
                if ([json isKindOfClass:NSDictionary.class] && [json[@"error"] isKindOfClass:NSString.class] &&
                    [json[@"error"] length] < 220) text = json[@"error"];
                reply(nil, accountError(status, text));
                return;
            }
            if (![json isKindOfClass:NSDictionary.class]) {
                reply(nil, accountError(status, @"The account server returned an invalid response."));
                return;
            }
            reply(json, nil);
        }] resume];
}

- (void)complete:(NSString*)bearer callback:(AciesCommunityResult)completion {
    if (!credential(bearer, @"acs_")) {
        completion(nil, accountError(0, @"The account server returned an invalid sign-in session."));
        return;
    }
    [self request:@"/community/session" method:@"GET" bearer:bearer payload:nil reply:
        ^(NSDictionary* info, NSError* error) {
            if (error) {
                completion(nil, error);
                return;
            }
            NSString* name = info[@"username"];
            NSNumber* user = info[@"userId"];
            if (![name isKindOfClass:NSString.class] || !name.length ||
                ![user isKindOfClass:NSNumber.class] || user.longLongValue <= 0) {
                completion(nil, accountError(0, @"The account server returned an invalid identity."));
                return;
            }

            // The existing community API exchanges the bearer for the credential used by SessionInfo
            // and the native TCP login. The official account password never enters guest memory.
            [self request:@"/api/client/login" method:@"POST" bearer:bearer payload:@{} reply:
                ^(NSDictionary* native, NSError* nativeError) {
                    if (nativeError) {
                        completion(nil, nativeError);
                        return;
                    }
                    NSDictionary* account = native[@"account"];
                    if (![account isKindOfClass:NSDictionary.class] ||
                        ![account[@"userId"] isEqual:user] || ![native[@"result"] isEqual:@0] ||
                        !credential(native[@"secret"], @"acp_")) {
                        completion(nil, accountError(0, @"The game server returned an invalid session."));
                        return;
                    }
                    auto session = [AciesCommunitySession new];
                    session.origin = self->_origin;
                    session.username = name;
                    session.userID = user.longLongValue;
                    session.bearer = bearer;
                    session.gatewaySecret = native[@"secret"];
                    completion(session, nil);
                }];
        }];
}

- (void)submit:(NSString*)path username:(NSString*)username password:(NSString*)password
        invite:(nullable NSString*)invite completion:(AciesCommunityResult)completion {
    NSMutableDictionary* body = [@{@"username": tidy(username), @"password": password} mutableCopy];
    if (invite) body[@"invite"] = tidy(invite);
    [self request:path method:@"POST" bearer:nil payload:body reply:^(NSDictionary* json, NSError* error) {
        if (error) completion(nil, error);
        else [self complete:json[@"token"] callback:completion];
    }];
}

- (void)signIn:(NSString*)username password:(NSString*)password completion:(AciesCommunityResult)completion {
    [self submit:@"/community/login" username:username password:password invite:nil completion:completion];
}

- (void)registerUser:(NSString*)username password:(NSString*)password invite:(NSString*)invite
          completion:(AciesCommunityResult)completion {
    [self submit:@"/community/register" username:username password:password invite:invite completion:completion];
}

- (void)resume:(NSString*)bearer completion:(AciesCommunityResult)completion {
    [self complete:bearer callback:completion];
}

@end
