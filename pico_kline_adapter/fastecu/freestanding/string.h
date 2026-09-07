/* Minimal ISO C declarations for the freestanding SH-2 kernel build. */
#ifndef D2WD_KERNEL_STRING_H
#define D2WD_KERNEL_STRING_H
#include <stddef.h>
void *memcpy(void *restrict destination, const void *restrict source, size_t count);
void *memset(void *destination, int value, size_t count);
int memcmp(const void *left, const void *right, size_t count);
#endif
