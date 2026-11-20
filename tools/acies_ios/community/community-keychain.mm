#import "community-keychain.h"
#import <Security/Security.h>

namespace {

NSDictionary* key(NSURL* origin) {
    return @{
        (__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
        (__bridge id)kSecAttrService: @"org.acies.community.session",
        (__bridge id)kSecAttrAccount: origin.absoluteString,
    };
}

} // namespace

NSDictionary<NSString*, NSString*>* AciesLoadCommunityKeychain(NSURL* origin) {
    NSMutableDictionary* query = [key(origin) mutableCopy];
    query[(__bridge id)kSecReturnData] = @YES;
    query[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
    CFTypeRef output = nullptr;
    if (SecItemCopyMatching((__bridge CFDictionaryRef)query, &output) != errSecSuccess || !output) return nil;
    NSData* data = CFBridgingRelease(output);
    if (![data isKindOfClass:NSData.class]) return nil;
    NSDictionary* record = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (![record isKindOfClass:NSDictionary.class] ||
        ![record[@"user"] isKindOfClass:NSString.class] ||
        ![record[@"bearer"] isKindOfClass:NSString.class]) return nil;
    return record;
}

BOOL AciesSaveCommunityKeychain(AciesCommunitySession* session) {
    NSData* value = [NSJSONSerialization dataWithJSONObject:@{@"user": session.username, @"bearer": session.bearer}
                                                  options:0 error:nil];
    if (!value) return NO;
    NSDictionary* query = key(session.origin);
    NSDictionary* changes = @{
        (__bridge id)kSecValueData: value,
        (__bridge id)kSecAttrAccessible: (__bridge id)kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
    };
    auto status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)changes);
    if (status != errSecItemNotFound) return status == errSecSuccess;
    NSMutableDictionary* item = [query mutableCopy];
    [item addEntriesFromDictionary:changes];
    status = SecItemAdd((__bridge CFDictionaryRef)item, nullptr);
    if (status == errSecDuplicateItem) {
        status = SecItemUpdate((__bridge CFDictionaryRef)query, (__bridge CFDictionaryRef)changes);
    }
    return status == errSecSuccess;
}

void AciesClearCommunityKeychain(NSURL* origin) {
    SecItemDelete((__bridge CFDictionaryRef)key(origin));
}
