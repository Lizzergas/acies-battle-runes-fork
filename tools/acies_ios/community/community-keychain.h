#import <Foundation/Foundation.h>
#import "community-auth.h"

NS_ASSUME_NONNULL_BEGIN

NSDictionary<NSString*, NSString*>* _Nullable AciesLoadCommunityKeychain(NSURL* origin);
BOOL AciesSaveCommunityKeychain(AciesCommunitySession* session);
void AciesClearCommunityKeychain(NSURL* origin);

NS_ASSUME_NONNULL_END
