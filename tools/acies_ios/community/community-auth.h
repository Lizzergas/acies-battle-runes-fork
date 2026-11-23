#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@class AciesCommunitySession;
typedef void (^AciesCommunityResult)(AciesCommunitySession* _Nullable, NSError* _Nullable);

@interface AciesCommunitySession : NSObject
@property(nonatomic, readonly) NSURL* origin;
@property(nonatomic, readonly) NSString* username;
@property(nonatomic, readonly) int64_t userID;
@property(nonatomic, readonly) NSString* bearer;
@property(nonatomic, readonly) NSString* gatewaySecret;
- (BOOL)prepareNativeStorage:(NSURL*)storage error:(NSError**)error;
@end

@interface AciesCommunityClient : NSObject
- (nullable instancetype)initWithOrigin:(NSURL*)origin allowLoopbackHTTP:(BOOL)allow;
- (void)signIn:(NSString*)username
      password:(NSString*)password
    completion:(AciesCommunityResult)completion;
- (void)registerUser:(NSString*)username
            password:(NSString*)password
              invite:(NSString*)invite
          completion:(AciesCommunityResult)completion;
- (void)resume:(NSString*)bearer completion:(AciesCommunityResult)completion;
@end

// Server trust for account and game HTTPS requests. Uses system trust unless a
// lab build bundled community-test-ca.der, in which case only that CA anchors
// the chain. Host name validation still applies either way.
void AciesCommunityEvaluateTrust(NSURLAuthenticationChallenge* challenge,
                                 void (^completion)(NSURLSessionAuthChallengeDisposition,
                                                    NSURLCredential* _Nullable));

NS_ASSUME_NONNULL_END
