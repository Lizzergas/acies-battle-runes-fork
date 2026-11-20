#include <jni.h>
#include <stdbool.h>
#include <stddef.h>

typedef struct { float x, y, width, height; } Rect;
typedef struct { float x, y, z; } Point;
typedef struct { float x, y, z, width, height, depth; } ZRect;
typedef struct { float red, green, blue, alpha; } Color;

enum { PICKER, SIGN_IN, REGISTER, CONTINUE };

typedef struct {
    void *owner;
    void *buttons[3];
    void *fields[3];
    int mode;
    bool layout_pending;
    bool request_pending;
    bool completed;
    char saved_name[24];
    char error[192];
} Picker;

extern Picker picker;
extern void *object_new(size_t size);
extern void object_autorelease(void *object);
extern void object_retain(void *object);
extern void object_release(void *object);
extern void layer_set_frame(void *layer, const Rect *frame);
extern void layer_add(void *layer, void *child);
extern void layer_remove(void *layer, bool transition);
extern void field_init(void *field);
extern void field_font(void *field, void *font);
extern void field_color(void *field, Color color);
extern void field_placeholder(void *field, const char *text);
extern void field_max(void *field, unsigned length);
extern void field_secure(void *field, bool secure);
extern void field_focus(void *field, bool focus);
extern void field_clear(void *field);
extern void *field_text(void *field);
extern const char *cstring(void *string);
extern const char *cstring_format(const char *format, ...);
extern const char *file_storage_path(const char *relative);
extern bool file_make_directory(const char *path);
extern const void *current_account;
extern void *system_font(float size, int style);
extern void graphics_push(void *graphics, bool mark);
extern void graphics_pop(void *graphics, bool mark);
extern void graphics_color(void *graphics, const Color *color, bool multiply);
extern void graphics_round_rect(void *graphics, const ZRect *rect, float radius, bool fill, unsigned corners);
extern void graphics_string_init(void *param, const char *text);
extern void graphics_string_destroy(void *param);
extern void graphics_string(void *graphics, const void *param, Point point, int alignment, float width);
extern void account_completed(void *handler, void *owner);
extern JNIEnv *game_jni_env(void);

const char *player_record_path(const char *relative) {
    const void *account = current_account;
    // Player::userId is the signed 64-bit field at 0x18 in Account's base.
    long player_id = account ? *(const long *)((const char *)account + 0x18) : 0;
    const char *directory = cstring_format("community-player-%ld", player_id);
    file_make_directory(file_storage_path(directory));
    if (relative[0] == 'r') {  // results/ or results/<transaction>.xmf
        file_make_directory(file_storage_path(cstring_format("%s/results", directory)));
    }
    return file_storage_path(cstring_format("%s/%s", directory, relative));
}

typedef struct {
    jclass type;
    jmethodID saved_name;
    jmethodID begin;
    jmethodID poll;
} JavaAccount;

extern JavaAccount account_java;

void bind_account_class(JNIEnv *env) {
    if (account_java.type) return;
    jclass cls = (*env)->FindClass(env, "org/acies/community/CommunitySession");
    if (!cls) {
        (*env)->ExceptionClear(env);
        return;
    }
    account_java.saved_name = (*env)->GetStaticMethodID(env, cls, "savedName", "()Ljava/lang/String;");
    account_java.begin = (*env)->GetStaticMethodID(env, cls, "begin", "(ILjava/lang/String;Ljava/lang/String;Ljava/lang/String;)V");
    account_java.poll = (*env)->GetStaticMethodID(env, cls, "poll", "()Ljava/lang/String;");
    if (account_java.saved_name && account_java.begin && account_java.poll) {
        account_java.type = (*env)->NewGlobalRef(env, cls);
    } else {
        (*env)->ExceptionClear(env);
    }
    (*env)->DeleteLocalRef(env, cls);
}

static void copy_text(char *dest, size_t size, const char *source) {
    size_t i = 0;
    if (source) for (; i + 1 < size && source[i]; i++) dest[i] = source[i];
    dest[i] = '\0';
}

static void copy_java_text(JNIEnv *env, jstring value, char *dest, size_t size) {
    const char *source = value ? (*env)->GetStringUTFChars(env, value, 0) : 0;
    copy_text(dest, size, source);
    if (source) (*env)->ReleaseStringUTFChars(env, value, source);
    if (value) (*env)->DeleteLocalRef(env, value);
}

static Rect frame(void *layer) {
    return *(const Rect *)((const char *)layer + 0x1b4);
}

static float control_width(Rect bounds) {
    return bounds.width < 680 ? bounds.width - 64 : 560;
}

static Rect control(Rect bounds, float y, float height) {
    float width = control_width(bounds);
    return (Rect){ (bounds.width - width) * 0.5f, y, width, height };
}

static float field_top(Rect bounds) {
    return bounds.height * 0.5f - (picker.mode == REGISTER ? 145 : 115);
}

static Rect field_box(Rect bounds, int index) {
    return control(bounds, field_top(bounds) + index * 70, 58);
}

static void select_mode(int mode) {
    for (int i = 0; i < 3; i++) {
        if (picker.fields[i]) {
            field_focus(picker.fields[i], false);
            if (i > 0) field_clear(picker.fields[i]);
            layer_remove(picker.fields[i], false);
            picker.fields[i] = 0;
        }
    }
    picker.mode = mode;
    picker.error[0] = '\0';
    picker.layout_pending = true;
}

static void add_field(int index, Rect box, const char *hint, unsigned limit) {
    void *field = object_new(0x280);  /* Native CSTextField size in ACIES 2.5.1. */
    field_init(field);
    object_autorelease(field);
    box.x += 16;
    box.width -= 32;
    layer_set_frame(field, &box);
    field_font(field, system_font(26, 0));
    field_color(field, (Color){ .08f, .08f, .09f, 1 });
    field_placeholder(field, hint);
    field_max(field, limit);
    if (index == 1) field_secure(field, true);
    layer_add(picker.owner, field);
    picker.fields[index] = field;
}

static void arrange_buttons(Rect bounds) {
    float submit = picker.mode == PICKER ? bounds.height * 0.5f - 62
                                       : field_top(bounds) + (picker.mode == REGISTER ? 3 : 2) * 70 + 3;
    const Rect hidden = { -900, -900, 0, 0 };
    for (int i = 0; i < 3; i++) {
        if (!picker.buttons[i]) continue;
        if (i == 2 && (picker.mode != PICKER || !picker.saved_name[0])) {
            layer_set_frame(picker.buttons[i], &hidden);
        } else {
            float y = picker.mode == PICKER ? submit + i * 96 : submit + i * 67;
            Rect rect = control(bounds, y, picker.mode == PICKER ? 74 : 57);
            layer_set_frame(picker.buttons[i], &rect);
        }
    }
}

static void paint_box(void *graphics, Rect rect, float radius) {
    Color white = { 1, 1, 1, 1 };
    ZRect box = { rect.x, rect.y, 0, rect.width, rect.height, 0 };
    graphics_color(graphics, &white, false);
    graphics_round_rect(graphics, &box, radius, true, 15);
}

static void paint_text(void *graphics, const char *text, Point at, float size, int style, Color color, float width) {
    unsigned long param[4] = { 0 };
    char *state = *(char **)((char *)graphics + 0x20);
    void **font_slot = (void **)(state + 0x60);
    void *font = system_font(size, style);
    if (*font_slot != font) {
        if (font) object_retain(font);
        if (*font_slot) object_release(*font_slot);
        *font_slot = font;
    }
    graphics_color(graphics, &color, false);
    graphics_string_init(param, text);
    graphics_string(graphics, param, at, 5, width);
    graphics_string_destroy(param);
}

static const char *caption(int i, char *saved, size_t size) {
    if (picker.mode != PICKER) return i == 0 ? (picker.mode == SIGN_IN ? "Sign in" : "Create account") : "Back";
    if (i == 0) return "Sign in";
    if (i == 1) return "Create account";
    copy_text(saved, size, "Continue as ");
    copy_text(saved + 12, size - 12, picker.saved_name);
    return saved;
}

static void draw_button(void *owner, void *button, void *graphics, int index) {
    if (picker.owner != owner || picker.completed) return;
    if (picker.buttons[index] != button) {
        picker.buttons[index] = button;
        picker.layout_pending = true;
    }
    if (index == 2 && (picker.mode != PICKER || !picker.saved_name[0])) return;
    Rect bounds = frame(button);
    graphics_push(graphics, false);
    paint_box(graphics, (Rect){ 0, 0, bounds.width, bounds.height }, 12);
    char saved[42];
    paint_text(graphics, caption(index, saved, sizeof(saved)), (Point){ bounds.width / 2, bounds.height / 2, 0 },
               picker.mode == PICKER ? 31 : 26, 1, (Color){ .06f, .06f, .07f, 1 }, bounds.width - 28);
    graphics_pop(graphics, false);
}

static jstring java_field(JNIEnv *env, int index) {
    const char *value = picker.fields[index] ? cstring(field_text(picker.fields[index])) : 0;
    return (*env)->NewStringUTF(env, value ? value : "");
}

static void begin_request(int mode) {
    if (!account_java.type) {
        copy_text(picker.error, sizeof(picker.error), "Cannot open ACIES accounts.");
        return;
    }
    JNIEnv *env = game_jni_env();
    if (!env) return;
    jstring username = java_field(env, 0);
    jstring password = java_field(env, 1);
    jstring invite = java_field(env, 2);
    (*env)->CallStaticVoidMethod(env, account_java.type, account_java.begin, mode, username, password, invite);
    (*env)->DeleteLocalRef(env, username);
    (*env)->DeleteLocalRef(env, password);
    (*env)->DeleteLocalRef(env, invite);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionClear(env);
        copy_text(picker.error, sizeof(picker.error), "Could not start sign-in. Try again.");
        return;
    }
    for (int i = 0; i < 3; i++) if (picker.fields[i]) field_focus(picker.fields[i], false);
    if (picker.fields[1]) field_clear(picker.fields[1]);
    copy_text(picker.error, sizeof(picker.error), "Connecting...");
    picker.request_pending = true;
}

static void click(void *owner, int index) {
    if (picker.owner != owner || picker.request_pending || picker.completed) return;
    if (picker.mode == PICKER) {
        if (index == 0) select_mode(SIGN_IN);
        if (index == 1) select_mode(REGISTER);
        if (index == 2 && picker.saved_name[0]) begin_request(CONTINUE);
    } else {
        if (index == 0) begin_request(picker.mode);
        if (index == 1) select_mode(PICKER);
    }
}

void draw_sign_in(void *owner, void *button, void *graphics) { draw_button(owner, button, graphics, 0); }
void draw_register(void *owner, void *button, void *graphics) { draw_button(owner, button, graphics, 1); }
void draw_continue(void *owner, void *button, void *graphics) { draw_button(owner, button, graphics, 2); }
void tap_sign_in(void *owner, void *button) { (void)button; click(owner, 0); }
void tap_register(void *owner, void *button) { (void)button; click(owner, 1); }
void tap_continue(void *owner, void *button) { (void)button; click(owner, 2); }

static void poll_request(void) {
    JNIEnv *env = game_jni_env();
    if (!env) return;
    jstring result = (*env)->CallStaticObjectMethod(env, account_java.type, account_java.poll);
    if (!result) return;
    picker.request_pending = false;
    copy_java_text(env, result, picker.error, sizeof(picker.error));
    if (!picker.error[0]) {
        select_mode(PICKER);
        picker.completed = true;
        account_completed((char *)picker.owner + 0x258, picker.owner);
    } else if (picker.mode == PICKER) {
        copy_java_text(env, (*env)->CallStaticObjectMethod(env, account_java.type, account_java.saved_name),
                       picker.saved_name, sizeof(picker.saved_name));
        picker.layout_pending = true;
    }
}

void draw_account_picker(void *owner, void *graphics) {
    if (picker.owner != owner) {
        picker = (Picker){ .owner = owner, .layout_pending = true };
        if (account_java.type) {
            JNIEnv *env = game_jni_env();
            if (env) copy_java_text(env, (*env)->CallStaticObjectMethod(env, account_java.type, account_java.saved_name),
                                    picker.saved_name, sizeof(picker.saved_name));
        }
    }
    if (picker.request_pending) poll_request();
    if (picker.completed) return;
    Rect bounds = frame(owner);
    if (picker.layout_pending) {
        picker.layout_pending = false;
        arrange_buttons(bounds);
        if (picker.mode != PICKER && !picker.fields[0]) {
            add_field(0, field_box(bounds, 0), "Username", 20);
            add_field(1, field_box(bounds, 1), "Password", 128);
            if (picker.mode == REGISTER) add_field(2, field_box(bounds, 2), "Invitation code, if required", 24);
        }
    }
    graphics_push(graphics, false);
    if (picker.mode != PICKER) {
        for (int i = 0; i < (picker.mode == REGISTER ? 3 : 2); i++) paint_box(graphics, field_box(bounds, i), 10);
    }
    float heading = picker.mode == PICKER ? bounds.height * .5f - 145 : field_top(bounds) - 52;
    const char *title = picker.mode == PICKER ? "ACIES account" : picker.mode == REGISTER ? "Create an account" : "Sign in";
    paint_text(graphics, title, (Point){ bounds.width / 2, heading, 0 }, 30, 1, (Color){ 1, 1, 1, 1 }, bounds.width - 32);
    if (picker.error[0]) {
        float y = picker.mode == PICKER ? bounds.height * .5f + 225
                                       : field_top(bounds) + (picker.mode == REGISTER ? 3 : 2) * 70 + 148;
        paint_text(graphics, picker.error, (Point){ bounds.width / 2, y, 0 }, 23, 0,
                   (Color){ 1, .84f, .8f, 1 }, bounds.width - 32);
    }
    graphics_pop(graphics, false);
}

void init_account_picker_frame(void *owner, const Rect *rect) {
    picker.owner = 0;
    layer_set_frame(owner, rect);
}
