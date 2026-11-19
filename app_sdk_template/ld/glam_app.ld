/* Linker script for G'lam OS dynamic Xtensa .elf Apps (loaded into ESP32-S3 PSRAM) */
ENTRY(glam_app_entry)

SECTIONS
{
    . = 0x0;

    .text ALIGN(16) : {
        *(.literal .text .literal.* .text.*)
        . = ALIGN(16);
    }

    .rodata ALIGN(16) : {
        *(.rodata .rodata.* .srodata .srodata.*)
        . = ALIGN(16);
    }

    .data ALIGN(16) : {
        *(.data .data.* .sdata .sdata.*)
        . = ALIGN(16);
    }

    .bss ALIGN(16) : {
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(16);
    }

    /DISCARD/ : {
        *(.note.GNU-stack)
    }
}
