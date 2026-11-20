#import <OpenGLES/EAGL.h>
#import <OpenGLES/ES3/gl.h>
#import <QuartzCore/QuartzCore.h>
#import <UIKit/UIKit.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <dlfcn.h>
#include <vector>
#include <unordered_map>
#include <cstdio>
#include <numeric>

#include "game-lifecycle.h"
#include "drawable-bridge.h"

namespace {

constexpr size_t measure_frames = 1800;
// All full-resolution diagnostic readbacks have finished by frame 120.
constexpr unsigned warmup_frames = 181;

void logMessage(const char* message) {
    std::fprintf(stderr, "%s\n", message);
    std::fflush(stderr);
}

NSString* testControlToken() {
    NSString* prefix = @"--acies-test-token=";
    for (NSString* argument in NSProcessInfo.processInfo.arguments) {
        if ([argument hasPrefix:prefix]) return [argument substringFromIndex:prefix.length];
    }
    return nil;
}

bool normalizedCoordinate(NSString* text, float* value) {
    NSScanner* scanner = [NSScanner scannerWithString:text];
    scanner.charactersToBeSkipped = nil;
    return [scanner scanFloat:value] && scanner.isAtEnd && std::isfinite(*value)
        && *value >= 0 && *value < 1;
}

uint64_t resolveEAGL(const char* name) {
    if (auto address = acies_aot_resolve_drawable_import(name)) return address;
    if (name[0] == 'g' && name[1] == 'l')
        return reinterpret_cast<uint64_t>(dlsym(RTLD_DEFAULT, name));
    return 0;
}

struct FrameTimes {
    std::array<double, measure_frames> intervals{};
    std::array<double, measure_frames> draws{};
    double last = 0;
    size_t count = 0;
    unsigned warmup = 0;

    void record(CFTimeInterval timestamp, double work_ms) {
        if (warmup < warmup_frames || last == 0) {
            ++warmup;
            last = timestamp;
            return;
        }
        if (count >= intervals.size()) return;
        intervals[count] = (timestamp - last) * 1000;
        draws[count] = work_ms;
        last = timestamp;
        ++count;
        if (count == intervals.size()) print();
    }

    void print() {
        double elapsed = std::accumulate(intervals.begin(), intervals.end(), 0.0);
        const auto slow = std::count_if(intervals.begin(), intervals.end(), [](double ms) {
            return ms > 25.0;
        });
        std::sort(intervals.begin(), intervals.end());
        std::sort(draws.begin(), draws.end());
        char report[512];
        std::snprintf(report, sizeof report,
            "ACIES AOT GAME PACING: %zu frames, %.2f fps, frame interval ms p50=%.3f p95=%.3f p99=%.3f max=%.3f, %ld intervals >25ms, draw+present CPU ms p50=%.3f p95=%.3f max=%.3f",
            count, 1000 * count / elapsed, intervals[count / 2 - 1],
            intervals[count * 95 / 100 - 1], intervals[count * 99 / 100 - 1], intervals.back(),
            long(slow), draws[count / 2 - 1], draws[count * 95 / 100 - 1], draws.back());
        logMessage(report);
    }
};

} // namespace

@interface ProbeView : UIView
- (BOOL)handleTestLink:(NSURL*)url;
@end

@implementation ProbeView {
    EAGLContext* _context;
    CADisplayLink* _link;
    GLuint _framebuffer, _color, _depthStencil;
    GLint _pixelWidth, _pixelHeight;
    BOOL _prepared, _failed;
    BOOL _testTapPending;
    unsigned _testTapGeneration;
    AciesTouch _testTap;
    unsigned _frameNumber;
    int32_t _nextTouchIdentifier;
    std::unordered_map<const void*, int32_t> _touchIdentifiers;
    FrameTimes _times;
}

+ (Class)layerClass {
    return CAEAGLLayer.class;
}

- (void)layoutSubviews {
    [super layoutSubviews];
    if (_failed || !self.window || CGRectIsEmpty(self.bounds)) return;
    self.multipleTouchEnabled = YES;
    self.contentScaleFactor = self.window.screen.scale;
    CAEAGLLayer* layer = (CAEAGLLayer*)self.layer;
    layer.opaque = YES;
    layer.drawableProperties = @{
        kEAGLDrawablePropertyColorFormat: kEAGLColorFormatRGBA8,
        kEAGLDrawablePropertyRetainedBacking: @NO
    };
    if (!_context) _context = [[EAGLContext alloc] initWithAPI:kEAGLRenderingAPIOpenGLES3];
    if (!_context || ![EAGLContext setCurrentContext:_context]) {
        [self stopWithMessage:"ACIES AOT GAME FAIL: iOS did not create an OpenGL ES 3 context."];
        return;
    }

    if (!_framebuffer) glGenFramebuffers(1, &_framebuffer);
    if (!_color) glGenRenderbuffers(1, &_color);
    glBindFramebuffer(GL_FRAMEBUFFER, _framebuffer);
    glBindRenderbuffer(GL_RENDERBUFFER, _color);
    if (![_context renderbufferStorage:GL_RENDERBUFFER fromDrawable:layer]) {
        [self stopWithMessage:"ACIES AOT GAME FAIL: drawable allocation was unsuccessful."];
        return;
    }
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, _color);
    glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_WIDTH, &_pixelWidth);
    glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_HEIGHT, &_pixelHeight);
    if (!_depthStencil) glGenRenderbuffers(1, &_depthStencil);
    glBindRenderbuffer(GL_RENDERBUFFER, _depthStencil);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, _pixelWidth, _pixelHeight);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, _depthStencil);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_STENCIL_ATTACHMENT, GL_RENDERBUFFER, _depthStencil);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        [self stopWithMessage:"ACIES AOT GAME FAIL: the drawable framebuffer is incomplete."];
        return;
    }
    acies_aot_set_drawable_framebuffer(_framebuffer);
    if (!_prepared) [self prepareProbe];
}

- (void)prepareProbe {
#if defined(ACIES_LOCAL_ADMISSION)
    NSDictionary<NSString*, NSString*>* localMock = @{
        @"AciesLocalMockHost": @"ACIES_LOCAL_MOCK_HOST",
        @"AciesLocalMockHTTPPort": @"ACIES_LOCAL_MOCK_PORT",
        @"AciesLocalMockGatewayPort": @"ACIES_LOCAL_MOCK_GATEWAY_PORT",
    };
    for (NSString* key in localMock) {
        id value = [NSBundle.mainBundle objectForInfoDictionaryKey:key];
        if ([value isKindOfClass:NSString.class] && !std::getenv(localMock[key].UTF8String))
            setenv(localMock[key].UTF8String, [value UTF8String], 0);
    }
#endif
    NSString* resources = NSBundle.mainBundle.resourcePath;
    NSString* assets = [resources stringByAppendingPathComponent:@"game-assets"];
    NSString* storage = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSString* engine = [resources stringByAppendingPathComponent:@"libcdkapp.so"];
    NSString* cxx = [resources stringByAppendingPathComponent:@"libc++_shared.so"];
    char report[2048] = {};
    if (acies_aot_game_start(engine.fileSystemRepresentation, cxx.fileSystemRepresentation,
                             assets.fileSystemRepresentation, storage.fileSystemRepresentation,
                             _pixelWidth, _pixelHeight, resolveEAGL, report, sizeof report)) {
        [self stopWithMessage:report];
        return;
    }
    logMessage(report);
    _prepared = YES;
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(terminateProbe:)
                                               name:UIApplicationWillTerminateNotification object:nil];
    _link = [CADisplayLink displayLinkWithTarget:self selector:@selector(drawFrame:)];
    _link.preferredFrameRateRange = CAFrameRateRangeMake(60, 60, 60);
    [_link addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
}

- (void)drawFrame:(CADisplayLink*)link {
    const double started = CACurrentMediaTime();
    if ([EAGLContext currentContext] != _context && ![EAGLContext setCurrentContext:_context]) {
        [self stopWithMessage:"ACIES AOT GAME FAIL: could not restore the graphics context."];
        return;
    }
    glBindFramebuffer(GL_FRAMEBUFFER, _framebuffer);
    acies_aot_set_drawable_framebuffer(_framebuffer);
    char report[512] = {};
    if (acies_aot_game_frame(report, sizeof report)) {
        [self stopWithMessage:report];
        return;
    }
    ++_frameNumber;
    if (_frameNumber == 1 || _frameNumber == 30 || _frameNumber == 60 || _frameNumber == 120) {
        glBindFramebuffer(GL_FRAMEBUFFER, _framebuffer);
        std::vector<uint8_t> pixels(static_cast<size_t>(_pixelWidth) * _pixelHeight * 4);
        glReadPixels(0, 0, _pixelWidth, _pixelHeight, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
        size_t nonBlack = 0;
        for (size_t i = 0; i < pixels.size(); i += 4) {
            if (pixels[i] || pixels[i + 1] || pixels[i + 2]) ++nonBlack;
        }
        std::snprintf(report, sizeof report,
                      "ACIES AOT GAME frame %u %dx%d: %zu non-black pixels, GL error 0x%x",
                      _frameNumber, _pixelWidth, _pixelHeight, nonBlack, glGetError());
        logMessage(report);
    }
    glBindRenderbuffer(GL_RENDERBUFFER, _color);
    if (![_context presentRenderbuffer:GL_RENDERBUFFER]) {
        [self stopWithMessage:"ACIES AOT GAME FAIL: could not present the drawable."];
        return;
    }
    _times.record(link.timestamp, (CACurrentMediaTime() - started) * 1000);
}

- (void)forwardTouches:(NSSet<UITouch*>*)touches phase:(AciesTouchPhase)phase {
    if (!_prepared || _failed) return;
    if (_testTapPending) [self finishTestTap:AciesTouchCancelled];
    std::vector<AciesTouch> points;
    points.reserve(touches.count);
    for (UITouch* touch in touches) {
        const void* key = (__bridge const void*)touch;
        auto identifier = _touchIdentifiers.find(key);
        if (phase == AciesTouchBegan && identifier == _touchIdentifiers.end()) {
            identifier = _touchIdentifiers.emplace(key, ++_nextTouchIdentifier).first;
        }
        if (identifier == _touchIdentifiers.end()) continue;
        CGPoint position = [touch locationInView:self];
        const auto x = static_cast<float>(position.x * _pixelWidth / self.bounds.size.width);
        const auto y = static_cast<float>(position.y * _pixelHeight / self.bounds.size.height);
        points.push_back({identifier->second, x, y});
        if (phase == AciesTouchEnded || phase == AciesTouchCancelled)
            _touchIdentifiers.erase(identifier);
    }
    acies_aot_game_queue_touches(phase, points.data(), points.size());
}

- (void)finishTestTap:(AciesTouchPhase)phase {
    if (!_testTapPending) return;
    _testTapPending = NO;
    ++_testTapGeneration;
    acies_aot_game_queue_touches(phase, &_testTap, 1);
}

- (BOOL)handleTestLink:(NSURL*)url {
    if (!_prepared || _failed || ![url.scheme isEqualToString:@"acies-standalone-test"]
        || url.query || url.fragment || url.user || url.port) return NO;
    NSString* token = testControlToken();
    NSArray<NSString*>* parts = url.pathComponents;
    if (token.length < 16 || parts.count < 2 || ![parts[1] isEqualToString:token]) return NO;
    if ([url.host isEqualToString:@"measure"] && parts.count == 2) {
        _times = {};
        _times.warmup = warmup_frames;
        logMessage("ACIES AOT manually started 1800-frame measurement");
        return YES;
    }
    if (![url.host isEqualToString:@"tap"] || parts.count != 4
        || _testTapPending || !_touchIdentifiers.empty()) return NO;
    float x = 0, y = 0;
    if (!normalizedCoordinate(parts[2], &x) || !normalizedCoordinate(parts[3], &y)) return NO;
    _testTap = {0, x * _pixelWidth, y * _pixelHeight};
    _testTapPending = YES;
    const unsigned generation = _testTapGeneration;
    acies_aot_game_queue_touches(AciesTouchBegan, &_testTap, 1);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 85 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        if (_testTapGeneration == generation) [self finishTestTap:AciesTouchEnded];
    });
    return YES;
}

- (void)touchesBegan:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
    (void)event;
    [self forwardTouches:touches phase:AciesTouchBegan];
}
- (void)touchesMoved:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
    (void)event;
    [self forwardTouches:touches phase:AciesTouchMoved];
}
- (void)touchesEnded:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
    (void)event;
    [self forwardTouches:touches phase:AciesTouchEnded];
}
- (void)touchesCancelled:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
    (void)event;
    [self forwardTouches:touches phase:AciesTouchCancelled];
}

- (void)terminateProbe:(NSNotification*)notification {
    (void)notification;
    [_link invalidate];
    _link = nil;
    if (!_prepared || _failed || ![EAGLContext setCurrentContext:_context]) return;
    char report[512] = {};
    (void)acies_aot_game_shutdown(report, sizeof report);
    logMessage(report);
    _prepared = NO;
}

- (void)stopWithMessage:(const char*)message {
    logMessage(message);
    _failed = YES;
    [_link invalidate];
    _link = nil;
}

@end

@interface ProbeDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end

@implementation ProbeDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
    (void)options;
    application.idleTimerDisabled = testControlToken().length >= 16;
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UIViewController* controller = [[UIViewController alloc] init];
    controller.view = [[ProbeView alloc] initWithFrame:self.window.bounds];
    controller.view.backgroundColor = [UIColor colorWithRed:0.08 green:0.17 blue:0.32 alpha:1.0];
    self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];
    return YES;
}

- (BOOL)application:(UIApplication*)application openURL:(NSURL*)url
            options:(NSDictionary<UIApplicationOpenURLOptionsKey,id>*)options {
    (void)application;
    (void)options;
    return [(ProbeView*)self.window.rootViewController.view handleTestLink:url];
}
@end

int main(int argc, char* argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass(ProbeDelegate.class));
    }
}
