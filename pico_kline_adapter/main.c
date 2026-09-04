// SPDX-License-Identifier: MIT
/*
 * Raw USB CDC to ANCEL AD310 K-line bridge for Raspberry Pi Pico.
 *
 * Based in part on the MIT-licensed Noltari/pico-uart-bridge architecture
 * (Copyright 2021 Alvaro Fernandez Rojas). Subaru framing and flashing remain
 * on the host; this firmware only transports bytes and serial settings.
 */

#include <stdbool.h>
#include <stdint.h>

#include "hardware/gpio.h"
#include "hardware/regs/uart.h"
#include "hardware/uart.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include "tusb.h"

#define PIN_TARGET_RESET 1u
#define PIN_KLINE_TX 4u
#define PIN_KLINE_RX 5u
#define PIN_LED PICO_DEFAULT_LED_PIN

#define KLINE_UART uart1
#define DEFAULT_BAUD 4800u
#define FIFO_SIZE 4096u
#define FIFO_MASK (FIFO_SIZE - 1u)

_Static_assert((FIFO_SIZE & FIFO_MASK) == 0u,
               "FIFO_SIZE must be a power of two");

typedef struct {
    uint8_t bytes[FIFO_SIZE];
    uint32_t head;
    uint32_t tail;
} byte_fifo_t;

static byte_fifo_t host_to_line;
static byte_fifo_t line_to_host;
static bool usb_mounted;
static bool break_active;
static bool break_indefinite;
static absolute_time_t break_deadline;
static bool coding_pending;
static cdc_line_coding_t pending_coding = {
    .bit_rate = DEFAULT_BAUD,
    .stop_bits = CDC_LINE_CODING_STOP_BITS_1,
    .parity = CDC_LINE_CODING_PARITY_NONE,
    .data_bits = 8,
};
static uint32_t error_count;

static inline uint32_t fifo_count(const byte_fifo_t *fifo) {
    return fifo->head - fifo->tail;
}

static inline uint32_t fifo_free(const byte_fifo_t *fifo) {
    return FIFO_SIZE - fifo_count(fifo);
}

static inline bool fifo_empty(const byte_fifo_t *fifo) {
    return fifo->head == fifo->tail;
}

static bool fifo_push(byte_fifo_t *fifo, uint8_t value) {
    if (fifo_free(fifo) == 0u) {
        return false;
    }
    fifo->bytes[fifo->head & FIFO_MASK] = value;
    fifo->head++;
    return true;
}

static inline uint8_t fifo_peek(const byte_fifo_t *fifo) {
    return fifo->bytes[fifo->tail & FIFO_MASK];
}

static inline void fifo_drop(byte_fifo_t *fifo, uint32_t count) {
    fifo->tail += count;
}

static void fifo_clear(byte_fifo_t *fifo) {
    fifo->head = 0u;
    fifo->tail = 0u;
}

static void set_break(bool asserted) {
    break_active = asserted;
    if (asserted) {
        // GP4 high turns Q5 on and forces K-line dominant/low.
        gpio_set_outover(PIN_KLINE_TX, GPIO_OVERRIDE_HIGH);
    } else {
        // Inverted UART idle produces GP4 low, leaving Q5 off.
        gpio_set_outover(PIN_KLINE_TX, GPIO_OVERRIDE_INVERT);
        break_indefinite = false;
        // Do not expose the UART's synthetic break/framing byte as K-line data.
        while (uart_is_readable(KLINE_UART)) (void)uart_getc(KLINE_UART);
        uart_get_hw(KLINE_UART)->rsr = 0u;
    }
}

static void apply_pending_coding(void) {
    if (!coding_pending || break_active || !fifo_empty(&host_to_line) ||
        (uart_get_hw(KLINE_UART)->fr & UART_UARTFR_BUSY_BITS) != 0u) {
        return;
    }

    uint32_t baud = pending_coding.bit_rate;
    uint data_bits = pending_coding.data_bits;
    uint stop_bits = 1u;
    uart_parity_t parity = UART_PARITY_NONE;

    if (baud < 300u || baud > 1000000u) {
        baud = DEFAULT_BAUD;
        error_count++;
    }
    if (data_bits < 5u || data_bits > 8u) {
        data_bits = 8u;
        error_count++;
    }
    if (pending_coding.stop_bits == CDC_LINE_CODING_STOP_BITS_2) {
        stop_bits = 2u;
    } else if (pending_coding.stop_bits != CDC_LINE_CODING_STOP_BITS_1) {
        error_count++;
    }
    if (pending_coding.parity == CDC_LINE_CODING_PARITY_ODD) {
        parity = UART_PARITY_ODD;
    } else if (pending_coding.parity == CDC_LINE_CODING_PARITY_EVEN) {
        parity = UART_PARITY_EVEN;
    } else if (pending_coding.parity != CDC_LINE_CODING_PARITY_NONE) {
        error_count++;
    }

    uart_set_format(KLINE_UART, data_bits, stop_bits, parity);
    (void)uart_set_baudrate(KLINE_UART, baud);
    coding_pending = false;
}

static void service_line_rx(void) {
    if (break_active) {
        while (uart_is_readable(KLINE_UART)) (void)uart_getc(KLINE_UART);
        uart_get_hw(KLINE_UART)->rsr = 0u;
        return;
    }

    if (uart_get_hw(KLINE_UART)->rsr != 0u) {
        error_count++;
        uart_get_hw(KLINE_UART)->rsr = 0u;
    }

    while (uart_is_readable(KLINE_UART)) {
        uint8_t value = (uint8_t)uart_getc(KLINE_UART);
        if (usb_mounted && !fifo_push(&line_to_host, value)) {
            error_count++;
            break;
        }
    }
}

static void service_usb_rx(void) {
    if (coding_pending) return;

    while (usb_mounted && tud_cdc_available() != 0u &&
           fifo_free(&host_to_line) != 0u) {
        uint8_t buffer[64];
        uint32_t amount = tud_cdc_available();
        if (amount > sizeof(buffer)) amount = sizeof(buffer);
        if (amount > fifo_free(&host_to_line)) amount = fifo_free(&host_to_line);
        amount = tud_cdc_read(buffer, amount);
        if (amount == 0u) break;
        for (uint32_t i = 0u; i < amount; ++i) {
            (void)fifo_push(&host_to_line, buffer[i]);
        }
    }
}

static void service_line_tx(void) {
    if (break_active) return;
    while (!fifo_empty(&host_to_line) && uart_is_writable(KLINE_UART)) {
        uart_putc_raw(KLINE_UART, fifo_peek(&host_to_line));
        fifo_drop(&host_to_line, 1u);
    }
}

static void service_usb_tx(void) {
    bool wrote = false;
    while (usb_mounted && !fifo_empty(&line_to_host)) {
        uint32_t amount = fifo_count(&line_to_host);
        uint32_t contiguous = FIFO_SIZE - (line_to_host.tail & FIFO_MASK);
        uint32_t available = tud_cdc_write_available();
        if (amount > contiguous) amount = contiguous;
        if (amount > available) amount = available;
        if (amount == 0u) break;
        uint32_t sent = tud_cdc_write(
            &line_to_host.bytes[line_to_host.tail & FIFO_MASK], amount);
        fifo_drop(&line_to_host, sent);
        wrote = wrote || (sent != 0u);
        if (sent != amount) break;
    }
    if (wrote) tud_cdc_write_flush();
}

static void service_status(void) {
    static absolute_time_t next_toggle;
    static bool state;

    if (break_active) {
        gpio_put(PIN_LED, 0u);
    } else if (error_count == 0u) {
        gpio_put(PIN_LED, usb_mounted ? 1u : 0u);
    } else if (time_reached(next_toggle)) {
        state = !state;
        gpio_put(PIN_LED, state ? 1u : 0u);
        next_toggle = make_timeout_time_ms(125u);
    }
}

void tud_mount_cb(void) {
    usb_mounted = true;
    fifo_clear(&host_to_line);
    fifo_clear(&line_to_host);
}

void tud_umount_cb(void) {
    usb_mounted = false;
    set_break(false);
    fifo_clear(&host_to_line);
    fifo_clear(&line_to_host);
}

void tud_suspend_cb(bool remote_wakeup_en) {
    (void)remote_wakeup_en;
    usb_mounted = false;
    set_break(false);
    fifo_clear(&host_to_line);
    fifo_clear(&line_to_host);
}

void tud_resume_cb(void) {
    usb_mounted = true;
}

void tud_cdc_line_state_cb(uint8_t instance, bool dtr, bool rts) {
    (void)instance;
    (void)dtr;
    (void)rts;
}

void tud_cdc_line_coding_cb(uint8_t instance,
                            const cdc_line_coding_t *coding) {
    (void)instance;
    pending_coding = *coding;
    coding_pending = true;
}

void tud_cdc_send_break_cb(uint8_t instance, uint16_t duration_ms) {
    (void)instance;
    if (duration_ms == 0u) {
        set_break(false);
    } else {
        set_break(true);
        break_indefinite = duration_ms == 0xffffu;
        if (!break_indefinite) break_deadline = make_timeout_time_ms(duration_ms);
    }
}

static void init_hardware(void) {
    // GP1 holds the original AD310 MCU in reset for the Pico's whole runtime.
    gpio_init(PIN_TARGET_RESET);
    gpio_put(PIN_TARGET_RESET, 0u);
    gpio_set_dir(PIN_TARGET_RESET, GPIO_OUT);

    uart_init(KLINE_UART, DEFAULT_BAUD);
    uart_set_format(KLINE_UART, 8u, 1u, UART_PARITY_NONE);
    uart_set_hw_flow(KLINE_UART, false, false);
    uart_set_fifo_enabled(KLINE_UART, true);

    // Set inversion while GP4 is still an input, then give it to UART. This
    // prevents a startup dominant pulse through the inverting Q5 transistor.
    gpio_init(PIN_KLINE_TX);
    gpio_pull_down(PIN_KLINE_TX);
    gpio_set_outover(PIN_KLINE_TX, GPIO_OVERRIDE_INVERT);
    gpio_set_function(PIN_KLINE_TX, GPIO_FUNC_UART);

    gpio_init(PIN_KLINE_RX);
    gpio_disable_pulls(PIN_KLINE_RX);
    gpio_set_function(PIN_KLINE_RX, GPIO_FUNC_UART);

    gpio_init(PIN_LED);
    gpio_put(PIN_LED, 0u);
    gpio_set_dir(PIN_LED, GPIO_OUT);
}

int main(void) {
    init_hardware();
    usb_serial_number_init();
    tusb_init();
    watchdog_enable(1000u, true);

    while (true) {
        watchdog_update();
        if (break_active && !break_indefinite && time_reached(break_deadline)) {
            set_break(false);
        }
        service_line_rx();
        tud_task();
        apply_pending_coding();
        service_usb_rx();
        service_line_tx();
        service_line_rx();
        service_usb_tx();
        service_status();
        tight_loop_contents();
    }
}
