#include "drawable-bridge.h"

#include <cstring>
#include <OpenGLES/ES3/gl.h>

namespace {

// The launcher sets this on the thread that owns the current EAGLContext.
thread_local GLuint drawable_framebuffer = 0;

void bindGuestFramebuffer(GLenum target, GLuint handle) {
    glBindFramebuffer(target, handle ? handle : drawable_framebuffer);
}

void getGuestInteger(GLenum param, GLint* values) {
    glGetIntegerv(param, values);
    if ((param == GL_DRAW_FRAMEBUFFER_BINDING || param == GL_READ_FRAMEBUFFER_BINDING) &&
        static_cast<GLuint>(*values) == drawable_framebuffer) {
        *values = 0;
    }
}

} // namespace

extern "C" void acies_aot_set_drawable_framebuffer(unsigned framebuffer) {
    drawable_framebuffer = framebuffer;
}

extern "C" uint64_t acies_aot_resolve_drawable_import(const char* name) {
    if (std::strcmp(name, "glBindFramebuffer") == 0) {
        return reinterpret_cast<uint64_t>(&bindGuestFramebuffer);
    }
    if (std::strcmp(name, "glGetIntegerv") == 0) {
        return reinterpret_cast<uint64_t>(&getGuestInteger);
    }
    return 0;
}
