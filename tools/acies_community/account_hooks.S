    .text
    .globl community_bind_entry
community_bind_entry:
    cbz x2, bind_account_class
    sub sp, sp, #0x70
    b original_receive_query
