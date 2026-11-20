#include "font-bridge.h"

#include <CoreGraphics/CoreGraphics.h>
#include <CoreText/CoreText.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

#include "arm64_context.h"
#include "jni_env.h"
#include "shim.h"

namespace {

template <typename T>
struct Release {
    void operator()(T value) const { if (value) CFRelease(value); }
};

template <typename T>
using CFPointer = std::unique_ptr<std::remove_pointer_t<T>, Release<T>>;

using Text = std::vector<UniChar>;
using Pixels = std::vector<uint8_t>;
using Metrics = std::vector<float>;

struct Font {
    std::vector<CFPointer<CTFontRef>> faces;
    float size;
};

struct Object {
    std::variant<Font, Text, Pixels, Metrics> content;
    size_t refs = 1;
};

struct CustomFace {
    std::string family;
    int style;
    CFPointer<CGFontRef> face;
};

std::mutex mutex;
std::vector<CustomFace> custom_faces;
std::unordered_map<uint64_t, std::unique_ptr<Object>> objects;

template <typename Value>
uint64_t retainObject(Value value) {
    auto item = std::make_unique<Object>(Object{std::move(value), 1});
    const auto address = reinterpret_cast<uint64_t>(item.get());
    objects.emplace(address, std::move(item));
    return address;
}

template <typename Value>
Value* object(uint64_t handle) {
    const auto it = objects.find(handle);
    return it == objects.end() ? nullptr : std::get_if<Value>(&it->second->content);
}

struct GuestVaList {
    uint64_t stack;
    uint64_t gp_top;
    uint64_t fp_top;
    int32_t gp_offset;
    int32_t fp_offset;
};
static_assert(sizeof(GuestVaList) == 32);

double nextDouble(GuestVaList& args) {
    const uint64_t address = args.fp_offset < 0 ? args.fp_top + args.fp_offset : args.stack;
    if (args.fp_offset < 0) args.fp_offset += 16;
    else args.stack += 8;
    double value = 0;
    if (address) std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof value);
    return value;
}

constexpr unsigned find_class = 6;
constexpr unsigned new_global_ref = 21;
constexpr unsigned delete_global_ref = 22;
constexpr unsigned delete_local_ref = 23;
constexpr unsigned new_object_v = 29;
constexpr unsigned get_method_id = 33;
constexpr unsigned get_static_method_id = 113;
constexpr unsigned call_static_object_v = 115;
constexpr unsigned call_static_void_v = 142;
constexpr unsigned new_string = 163;
constexpr unsigned array_length = 171;
constexpr unsigned new_float_array = 181;
constexpr unsigned byte_array_region = 200;
constexpr unsigned float_array_region = 205;

enum Type { font_class, raster_class, system_font, named_font, load, measure, rasterize };
std::array<char, 7> tokens{};
std::array<ArcCtxFn, 256> previous{};
thread_local unsigned active_metric_fields = 0;

uint64_t token(Type type) {
    return reinterpret_cast<uint64_t>(&tokens[type]);
}

bool is(const char* actual, const char* expected) {
    return actual && std::strcmp(actual, expected) == 0;
}

void loadFace(const char* family, int style, const char* guest_path) {
    if (!family || !guest_path || !*guest_path) return;
    std::string path(guest_path);
    if (path.find("..") != std::string::npos) return;
    if (path.compare(0, 7, "assets/") == 0) {
        if (!arc::ShimAssetRoot()) return;
        path = std::string(arc::ShimAssetRoot()) + "/" + path.substr(7);
    }
    CFPointer<CGDataProviderRef> provider(CGDataProviderCreateWithFilename(path.c_str()));
    if (!provider) return;
    CFPointer<CGFontRef> face(CGFontCreateWithDataProvider(provider.get()));
    if (face) custom_faces.push_back({family, style, std::move(face)});
}

Font makeFont(const char* family, int style, double size) {
    Font font{{}, float(std::isfinite(size) ? std::clamp(size, 1.0, 512.0) : 14.0)};
    for (const auto& record : custom_faces) {
        if (family && record.family == family && record.style == style) {
            font.faces.emplace_back(CTFontCreateWithGraphicsFont(record.face.get(), font.size,
                                                                  nullptr, nullptr));
        }
    }

    auto fallback = CFPointer<CTFontRef>(CTFontCreateUIFontForLanguage(kCTFontUIFontSystem, font.size, nullptr));
    if (fallback && style > 0 && style < 4) {
        const CTFontSymbolicTraits traits = ((style & 1) ? kCTFontBoldTrait : 0) |
                                           ((style & 2) ? kCTFontItalicTrait : 0);
        auto changed = CFPointer<CTFontRef>(CTFontCreateCopyWithSymbolicTraits(
            fallback.get(), font.size, nullptr, traits, traits));
        if (changed) fallback = std::move(changed);
    }
    if (fallback) font.faces.push_back(std::move(fallback));
    return font;
}

struct GlyphLine {
    CFPointer<CTLineRef> line;
    float width = 0;
    float ascent = 0;
    float descent = 0;
};

GlyphLine glyphLine(const Font& font, const Text& chars) {
    if (font.faces.empty() || chars.empty()) return {};
    CTFontRef face = font.faces.back().get();
    std::vector<CGGlyph> glyphs(chars.size());
    for (const auto& candidate : font.faces) {
        if (candidate && CTFontGetGlyphsForCharacters(candidate.get(), chars.data(),
                                                     glyphs.data(), chars.size())) {
            face = candidate.get();
            break;
        }
    }
    CFPointer<CFStringRef> text(CFStringCreateWithCharacters(nullptr, chars.data(), chars.size()));
    if (!text || !face) return {};
    const void* keys[] = {kCTFontAttributeName, kCTForegroundColorFromContextAttributeName};
    const void* values[] = {face, kCFBooleanTrue};
    CFPointer<CFDictionaryRef> attrs(CFDictionaryCreate(nullptr, keys, values, 2,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks));
    CFPointer<CFAttributedStringRef> styled(CFAttributedStringCreate(nullptr, text.get(), attrs.get()));
    CFPointer<CTLineRef> line(CTLineCreateWithAttributedString(styled.get()));
    const float width = float(CTLineGetTypographicBounds(line.get(), nullptr, nullptr, nullptr));
    return {std::move(line), width, float(CTFontGetAscent(face)), float(CTFontGetDescent(face))};
}

Pixels raster(const GlyphLine& glyph, float font_size, Metrics& metrics) {
    if (!glyph.line || glyph.width <= 0 || glyph.width > 4096 || glyph.ascent + glyph.descent > 4096) return {};
    const auto width = size_t(std::ceil(glyph.width));
    const auto height = size_t(std::ceil(glyph.ascent + glyph.descent));
    if (height == 0) return {};
    Pixels pixels(width * height * 4);
    CFPointer<CGColorSpaceRef> color(CGColorSpaceCreateWithName(kCGColorSpaceSRGB));
    CFPointer<CGContextRef> bitmap(CGBitmapContextCreate(pixels.data(), width, height, 8, width * 4,
        color.get(), kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big));
    if (!bitmap) return {};
    CGContextSetRGBFillColor(bitmap.get(), 1, 1, 1, 1);
    CGContextSetShouldAntialias(bitmap.get(), true);
    CGContextSetTextPosition(bitmap.get(), 0, height - glyph.ascent);
    CTLineDraw(glyph.line.get(), bitmap.get());
    metrics[0] = float(width);
    metrics[1] = float(height);
    metrics[2] = font_size - glyph.ascent;
    return pixels;
}

template <unsigned Slot>
bool handle(Arm64Ctx* c) {
    if constexpr (Slot == find_class) {
        const char* name = reinterpret_cast<const char*>(c->x[1]);
        if (is(name, "kr/co/brgames/cdk/CSFont")) c->x[0] = token(font_class);
        else if (is(name, "kr/co/brgames/cdk/CSRaster")) c->x[0] = token(raster_class);
        else return false;
    } else if constexpr (Slot == new_global_ref || Slot == delete_global_ref || Slot == delete_local_ref) {
        uint64_t ref = c->x[1];
        if (ref == token(font_class) || ref == token(raster_class)) {
            c->x[0] = Slot == new_global_ref ? ref : 0;
            return true;
        }
        const auto it = objects.find(ref);
        if (it == objects.end()) return false;
        c->x[0] = 0;
        if constexpr (Slot == new_global_ref) {
            ++it->second->refs;
            c->x[0] = ref;
        } else if (--it->second->refs == 0) objects.erase(it);
    } else if constexpr (Slot == get_method_id || Slot == get_static_method_id) {
        const uint64_t clazz = c->x[1];
        const char* name = reinterpret_cast<const char*>(c->x[2]);
        const char* sig = reinterpret_cast<const char*>(c->x[3]);
        if constexpr (Slot == get_method_id) {
            if (clazz != token(font_class) || !is(name, "<init>")) return false;
            if (is(sig, "(FI)V")) c->x[0] = token(system_font);
            else if (is(sig, "(Ljava/lang/String;FI)V")) c->x[0] = token(named_font);
            else return false;
        } else {
            if (clazz == token(font_class) && is(name, "load") &&
                is(sig, "(Ljava/lang/String;ILjava/lang/String;)V")) c->x[0] = token(load);
            else if (clazz == token(raster_class) && is(name, "characterSize") &&
                     is(sig, "(Lkr/co/brgames/cdk/CSFont;Ljava/lang/String;[F)V")) {
                c->x[0] = token(measure);
                active_metric_fields = 2;
            } else if (clazz == token(raster_class) && is(name, "createRasterFromCharacter") &&
                       is(sig, "(Lkr/co/brgames/cdk/CSFont;Ljava/lang/String;[F)[B")) {
                c->x[0] = token(rasterize);
                active_metric_fields = 3;
            } else return false;
        }
    } else if constexpr (Slot == new_object_v) {
        const bool named = c->x[2] == token(named_font);
        if ((!named && c->x[2] != token(system_font)) || !c->x[3]) return false;
        GuestVaList args{};
        std::memcpy(&args, reinterpret_cast<void*>(c->x[3]), sizeof args);
        const char* family = named ? reinterpret_cast<const char*>(arc::ShimVaNextInt(&args)) : nullptr;
        const double size = nextDouble(args);
        const int style = int(arc::ShimVaNextInt(&args));
        c->x[0] = retainObject(makeFont(family, style, size));
    } else if constexpr (Slot == new_string) {
        if (!active_metric_fields) return false;
        const auto* ptr = reinterpret_cast<const UniChar*>(c->x[1]);
        const auto size = uint32_t(c->x[2]);
        if ((!ptr && size) || size > 4096) return false;
        c->x[0] = retainObject(size ? Text(ptr, ptr + size) : Text{});
    } else if constexpr (Slot == new_float_array) {
        const auto size = uint32_t(c->x[1]);
        if (!active_metric_fields || size != active_metric_fields) return false;
        c->x[0] = retainObject(Metrics(size));
    } else if constexpr (Slot == call_static_void_v || Slot == call_static_object_v) {
        if (!c->x[3]) return false;
        GuestVaList args{};
        std::memcpy(&args, reinterpret_cast<void*>(c->x[3]), sizeof args);
        if constexpr (Slot == call_static_void_v) {
            if (c->x[2] == token(load)) {
                const auto* family = reinterpret_cast<const char*>(arc::ShimVaNextInt(&args));
                int style = int(arc::ShimVaNextInt(&args));
                const auto* path = reinterpret_cast<const char*>(arc::ShimVaNextInt(&args));
                loadFace(family, style, path);
                c->x[0] = 0;
                return true;
            }
            if (c->x[2] != token(measure)) return false;
        } else if (c->x[2] != token(rasterize)) return false;
        active_metric_fields = 0;
        const auto* font = object<Font>(arc::ShimVaNextInt(&args));
        const auto* text = object<Text>(arc::ShimVaNextInt(&args));
        auto* metrics = object<Metrics>(arc::ShimVaNextInt(&args));
        c->x[0] = 0;
        if (!font || !text || !metrics || metrics->size() < (Slot == call_static_void_v ? 2 : 3)) return true;
        auto glyph = glyphLine(*font, *text);
        if constexpr (Slot == call_static_void_v) {
            (*metrics)[0] = glyph.width;
            (*metrics)[1] = glyph.width > 0 ? glyph.ascent + glyph.descent : 0;
        } else {
            auto pixels = raster(glyph, font->size, *metrics);
            if (!pixels.empty()) c->x[0] = retainObject(std::move(pixels));
        }
    } else if constexpr (Slot == array_length) {
        const auto* pixels = object<Pixels>(c->x[1]);
        if (pixels) c->x[0] = pixels->size();
        else if (const auto* metrics = object<Metrics>(c->x[1])) c->x[0] = metrics->size();
        else return false;
    } else if constexpr (Slot == float_array_region || Slot == byte_array_region) {
        using Values = std::conditional_t<Slot == float_array_region, Metrics, Pixels>;
        const auto* array = object<Values>(c->x[1]);
        if (!array) return false;
        const auto start = uint32_t(c->x[2]);
        const auto count = uint32_t(c->x[3]);
        if (c->x[4] && start <= array->size() && count <= array->size() - start) {
            std::memcpy(reinterpret_cast<void*>(c->x[4]), array->data() + start,
                        count * sizeof(typename Values::value_type));
        }
        c->x[0] = 0;
    }
    return true;
}

template <unsigned Slot>
void call(Arm64Ctx* ctx) {
    {
        std::lock_guard guard(mutex);
        if (handle<Slot>(ctx)) return;
    }
    previous[Slot](ctx);
}

template <unsigned Slot>
void install(const char* name) {
    if (previous[Slot]) return;
    auto* table = reinterpret_cast<uint64_t*>(*reinterpret_cast<const uint64_t*>(arc_jni_env()));
    previous[Slot] = reinterpret_cast<ArcCtxFn>(table[Slot]);
    table[Slot] = reinterpret_cast<uint64_t>(&call<Slot>);
    arc_register_ctx_native(table[Slot], name, &call<Slot>);
}

} // namespace

extern "C" void acies_aot_install_font_jni(void) {
    install<find_class>("FindClass.font");
    install<new_global_ref>("NewGlobalRef.font");
    install<delete_global_ref>("DeleteGlobalRef.font");
    install<delete_local_ref>("DeleteLocalRef.font");
    install<new_object_v>("NewObjectV.font");
    install<get_method_id>("GetMethodID.font");
    install<get_static_method_id>("GetStaticMethodID.font");
    install<call_static_object_v>("CallStaticObjectMethodV.font");
    install<call_static_void_v>("CallStaticVoidMethodV.font");
    install<new_string>("NewString.font");
    install<array_length>("GetArrayLength.font");
    install<new_float_array>("NewFloatArray.font");
    install<byte_array_region>("GetByteArrayRegion.font");
    install<float_array_region>("GetFloatArrayRegion.font");
}
