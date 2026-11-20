#import <UIKit/UIKit.h>
#import "community-auth.h"

NS_ASSUME_NONNULL_BEGIN

typedef NSError* _Nullable (^AciesCommunityReady)(AciesCommunitySession* session);

@interface AciesCommunityForm : UIViewController
- (nullable instancetype)initWithOrigin:(NSURL*)origin
                      allowLoopbackHTTP:(BOOL)allow
                                  ready:(AciesCommunityReady)ready;
@end

NS_ASSUME_NONNULL_END
