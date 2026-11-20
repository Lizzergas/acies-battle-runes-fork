#!/usr/bin/env python3
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("original", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
source = args.original.read_text()
if args.original.resolve() == args.output.resolve():
    parser.error("Use a different output path for the host wrapper.")

def replace(old: str, new: str) -> None:
    global source
    if source.count(old) != 1:
        parser.error("The original game wrapper did not match the expected shape.")
    source = source.replace(old, new, 1)

replace('#include "game-lifecycle.h"', '''#include "game-lifecycle.h"
#include "community-native-http.h"
#include "community-gateway-mode.h"
#import "community-form.h"
#import "community-keychain.h"''')
replace('@interface ProbeView : UIView\n', '''@interface ProbeView : UIView
@property(nonatomic, copy) NSString* communityStorage;
''')
replace('NSString* storage = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;',
        'NSString* storage = self.communityStorage;')
replace('''    UIViewController* controller = [[UIViewController alloc] init];
    controller.view = [[ProbeView alloc] initWithFrame:self.window.bounds];
    controller.view.backgroundColor = [UIColor colorWithRed:0.08 green:0.17 blue:0.32 alpha:1.0];
    self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];
    return YES;''', '''    auto info = NSBundle.mainBundle.infoDictionary;
    NSString* endpoint = info[@"AciesCommunityOrigin"];
    const BOOL fixture = [info[@"AciesCommunitySyntheticLoopback"] boolValue];
    const unsigned gatewayPort = [info[@"AciesCommunityLocalGatewayPort"] unsignedIntValue];
    NSURL* origin = [NSURL URLWithString:endpoint ?: @""];
    __weak ProbeDelegate* weakSelf = self;
    AciesCommunityForm* form = [[AciesCommunityForm alloc] initWithOrigin:origin
        allowLoopbackHTTP:fixture ready:^NSError*(AciesCommunitySession* session) {
        ProbeDelegate* app = weakSelf;
        if (!app) return [NSError errorWithDomain:@"AciesCommunityHost" code:1
                                         userInfo:@{NSLocalizedDescriptionKey: @"The game window is unavailable."}];
        NSURL* documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory
                                                                inDomains:NSUserDomainMask].firstObject;
        NSString* directory = [NSString stringWithFormat:@"community-player-%lld", (long long)session.userID];
        NSURL* storage = [documents URLByAppendingPathComponent:directory isDirectory:YES];
        NSError* error = nil;
        if (![session prepareNativeStorage:storage error:&error]) return error ?:
            [NSError errorWithDomain:@"AciesCommunityHost" code:2
                            userInfo:@{NSLocalizedDescriptionKey: @"Could not prepare the native game session."}];
        if (!fixture && !AciesSaveCommunityKeychain(session)) {
            return [NSError errorWithDomain:@"AciesCommunityHost" code:3
                                   userInfo:@{NSLocalizedDescriptionKey: @"Could not save your session in Keychain."}];
        }
        if (!acies_aot_bind_community_native_http(session, gatewayPort)) {
            return [NSError errorWithDomain:@"AciesCommunityHost" code:4
                                   userInfo:@{NSLocalizedDescriptionKey: @"Could not initialize the game connection."}];
        }
        acies_aot_use_community_gateway(true);
        auto controller = [UIViewController new];
        ProbeView* game = [[ProbeView alloc] initWithFrame:app.window.bounds];
        game.communityStorage = storage.path;
        game.backgroundColor = [UIColor colorWithRed:0.08 green:0.17 blue:0.32 alpha:1.0];
        controller.view = game;
        app.window.rootViewController = controller;
        return nil;
    }];
    if (form) {
        self.window.rootViewController = form;
    } else {
        auto controller = [UIViewController new];
        UILabel* explanation = [UILabel new];
        explanation.text = @"The configured ACIES community server is invalid.";
        explanation.textAlignment = NSTextAlignmentCenter;
        explanation.numberOfLines = 0;
        controller.view.backgroundColor = UIColor.systemBackgroundColor;
        explanation.translatesAutoresizingMaskIntoConstraints = NO;
        [controller.view addSubview:explanation];
        auto area = controller.view.safeAreaLayoutGuide;
        [NSLayoutConstraint activateConstraints:@[
            [explanation.centerYAnchor constraintEqualToAnchor:area.centerYAnchor],
            [explanation.leadingAnchor constraintEqualToAnchor:area.leadingAnchor constant:32],
            [explanation.trailingAnchor constraintEqualToAnchor:area.trailingAnchor constant:-32],
        ]];
        self.window.rootViewController = controller;
    }
    [self.window makeKeyAndVisible];
    return YES;''')
args.output.write_text(source)
