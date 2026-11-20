.text
.global arcade_add_control
arcade_add_control:
    sub sp, sp, #112
    stp x29, x30, [sp, #48]
    stp x19, x20, [sp, #64]
    stp x21, x22, [sp, #80]
    stp x25, x27, [sp, #96]
    add x29, sp, #48
    mov x19, x0
    mov x25, x1
    adrp x27, draw_delegate_slot
    ldr x27, [x27, :lo12:draw_delegate_slot]
    adr x8, .Lbutton_ready
    str x8, [sp, #40]
    b button_constructor
.Lbutton_ready:
    mov x0, x21
    ldp x25, x27, [sp, #96]
    ldp x21, x22, [sp, #80]
    ldp x19, x20, [sp, #64]
    ldp x29, x30, [sp, #48]
    add sp, sp, #112
    ret

.global arcade_draw_control
arcade_draw_control:
    stp x23, x24, [sp, #-32]!
    str x30, [sp, #16]
    mov x23, x1
    mov x24, x3
    bl button_draw
    ldr x30, [sp, #16]
    ldp x23, x24, [sp], #32
    ret

.global debug_settings_hook
debug_settings_hook:
    blr x8
    mov x0, x19
    bl debug_add_tab
    b option_after_contact

.global debug_return_hook
debug_return_hook:
    cmp w21, #30
    b.ne .Loriginal_return
    mov x0, x20
    ldr x1, [x25]
    bl debug_return
    b lobby_after_rewards
.Loriginal_return:
    mov w0, #0x258
    b original_map_test_return

.global arcade_update_hook
arcade_update_hook:
    stp x0, x1, [sp, #-32]!
    stp x2, x30, [sp, #16]
    bl arcade_update
    ldp x2, x30, [sp, #16]
    ldp x0, x1, [sp], #32
    sub sp, sp, #0x70
    b original_update
