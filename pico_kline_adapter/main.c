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
#include "hardware/regs/io_bank0.h"
#include "hardware/regs/uart.h"
#include "hardware/structs/io_bank0.h"
#include "hardware/uart.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include "tusb.h"

#define PIN_TARGET_RESET 1u
#define PIN_STATUS_LED 2u
#define PIN_KLINE_TX 4u
#define PIN_KLINE_RX 5u
#define PIN_RX_LED 26u
#define PIN_TX_LED 27u
#define PIN_ONBOARD_LED PICO_DEFAULT_LED_PIN

#define KLINE_UART uart1
#define DEFAULT_BAUD 4800u
#define FIFO_SIZE 4096u
#define FIFO_MASK (FIFO_SIZE - 1u)
#define ACTIVITY_PULSE_MS 35u
#define DIAGNOSTIC_REQUEST 0x40u
#define DIAGNOSTIC_MAGIC 0x31444c4bu // Little-endian bytes "KLD1".
#define FIRMWARE_VERSION 0x00010102u // Major, minor, patch: 1.1.2.

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
// Diagnostic counters wrap modulo 2^32 and are never added to the CDC stream.
static uint32_t actual_baud;
static uint32_t host_rx_bytes;
static uint32_t uart_tx_bytes;
static uint32_t uart_rx_bytes;
static uint32_t usb_tx_queued_bytes;
static uint32_t uart_error_bits;
static bool tx_led_on;
static bool rx_led_on;
static absolute_time_t tx_led_deadline;
static absolute_time_t rx_led_deadline;

static void note_tx_activity(void) {
    gpio_put(PIN_TX_LED, 1u);
    tx_led_on = true;
    tx_led_deadline = make_timeout_time_ms(ACTIVITY_PULSE_MS);
}

static void note_rx_activity(void) {
    gpio_put(PIN_RX_LED, 1u);
    rx_led_on = true;
    rx_led_deadline = make_timeout_time_ms(ACTIVITY_PULSE_MS);
}

static void service_activity_leds(void) {
    if (tx_led_on && time_reached(tx_led_deadline)) {
        gpio_put(PIN_TX_LED, 0u);
        tx_led_on = false;
    }
    if (rx_led_on && time_reached(rx_led_deadline)) {
        gpio_put(PIN_RX_LED, 0u);
        rx_led_on = false;
    }
}

static void set_status_leds(bool on) {
    gpio_put(PIN_STATUS_LED, on ? 1u : 0u);
    gpio_put(PIN_ONBOARD_LED, on ? 1u : 0u);
}

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
    actual_baud = uart_set_baudrate(KLINE_UART, baud);
    coding_pending = false;
}

static void service_line_rx(void) {
    if (break_active) {
        while (uart_is_readable(KLINE_UART)) (void)uart_getc(KLINE_UART);
        uart_get_hw(KLINE_UART)->rsr = 0u;
        return;
    }

    uint32_t errors = uart_get_hw(KLINE_UART)->rsr;
    if (errors != 0u) {
        uart_error_bits |= errors;
        error_count++;
        uart_get_hw(KLINE_UART)->rsr = 0u;
    }

    bool received = false;
    while (uart_is_readable(KLINE_UART)) {
        uint8_t value = (uint8_t)uart_getc(KLINE_UART);
        uart_rx_bytes++;
        received = true;
        if (usb_mounted && !fifo_push(&line_to_host, value)) {
            error_count++;
            break;
        }
    }
    if (received) note_rx_activity();
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
        host_rx_bytes += amount;
        for (uint32_t i = 0u; i < amount; ++i) {
            (void)fifo_push(&host_to_line, buffer[i]);
        }
    }
}

static void service_line_tx(void) {
    if (break_active) return;
    bool transmitted = false;
    while (!fifo_empty(&host_to_line) && uart_is_writable(KLINE_UART)) {
        uart_putc_raw(KLINE_UART, fifo_peek(&host_to_line));
        uart_tx_bytes++;
        fifo_drop(&host_to_line, 1u);
        transmitted = true;
    }
    if (transmitted) note_tx_activity();
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
        usb_tx_queued_bytes += sent;
        fifo_drop(&line_to_host, sent);
        wrote = wrote || (sent != 0u);
        if (sent != amount) break;
    }
    if (wrote) tud_cdc_write_flush();
}

static void service_status(void) {
    static absolute_time_t next_toggle;
    static bool state;
    static bool error_was_active;

    if (error_count == 0u) {
        error_was_active = false;
        state = !usb_mounted;
        set_status_leds(state);
    } else if (!error_was_active) {
        state = true;
        set_status_leds(true);
        next_toggle = make_timeout_time_ms(125u);
        error_was_active = true;
    } else if (time_reached(next_toggle)) {
        state = !state;
        set_status_leds(state);
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

// Read-only device-level USB control request. No GPIO changes, UART reads,
// counter resets, or diagnostic text on the vehicle's raw CDC data channel.
// This is serviced by tud_task() on the main core, so counters and queues are
// stable while this snapshot is assembled. Pin levels are digital samples,
// not voltage measurements. See DIAGNOSTICS.md for the versioned wire format.
bool tud_vendor_control_xfer_cb(uint8_t rhport, uint8_t stage,
                               const tusb_control_request_t *request) {
    static uint32_t report[16];
    _Static_assert(sizeof(report) == 64u, "Diagnostic ABI must remain 64 bytes");

    if (request->bmRequestType != 0xc0u ||
        request->bRequest != DIAGNOSTIC_REQUEST ||
        request->wValue != 0u || request->wIndex != 0u ||
        request->wLength != sizeof(report)) {
        return false;
    }
    if (stage != CONTROL_STAGE_SETUP) return true;

    uint32_t flags = (usb_mounted ? 1u : 0u) |
                     (tud_ready() ? 2u : 0u) |
                     ((uint32_t)(tud_cdc_get_line_state() & 3u) << 2u) |
                     (break_active ? 16u : 0u) |
                     (coding_pending ? 32u : 0u) |
                     (gpio_get(PIN_KLINE_TX) ? 64u : 0u) |
                     (gpio_get(PIN_KLINE_RX) ? 128u : 0u);
    report[0] = DIAGNOSTIC_MAGIC;
    report[1] = FIRMWARE_VERSION;
    report[2] = to_ms_since_boot(get_absolute_time());
    report[3] = flags;
    report[4] = io_bank0_hw->io[PIN_KLINE_TX].ctrl;
    report[5] = io_bank0_hw->io[PIN_KLINE_RX].ctrl;
    report[6] = pending_coding.bit_rate;
    report[7] = actual_baud;
    report[8] = host_rx_bytes;
    report[9] = uart_tx_bytes;
    report[10] = uart_rx_bytes;
    report[11] = usb_tx_queued_bytes;
    report[12] = error_count;
    report[13] = uart_error_bits;
    report[14] = fifo_count(&host_to_line);
    report[15] = fifo_count(&line_to_host);
    return tud_control_xfer(rhport, request, report, sizeof(report));
}

static void init_hardware(void) {
    // GP1 holds the original AD310 MCU in reset for the Pico's whole runtime.
    gpio_init(PIN_TARGET_RESET);
    gpio_put(PIN_TARGET_RESET, 0u);
    gpio_set_dir(PIN_TARGET_RESET, GPIO_OUT);

    actual_baud = uart_init(KLINE_UART, DEFAULT_BAUD);
    uart_set_format(KLINE_UART, 8u, 1u, UART_PARITY_NONE);
    uart_set_hw_flow(KLINE_UART, false, false);
    uart_set_fifo_enabled(KLINE_UART, true);

    // Select UART and inverted TX together while GP4 is still an input.
    // gpio_set_function() clears ALL overrides, so calling it after
    // gpio_set_outover(INVERT) silently restores normal polarity and holds
    // K-line low at idle. An atomic CTRL update also avoids a dominant pulse
    // between selecting UART and enabling inversion (AD310 Q5 / Jaycar Q1).
    gpio_init(PIN_KLINE_TX);
    gpio_pull_down(PIN_KLINE_TX);
    hw_write_masked(&io_bank0_hw->io[PIN_KLINE_TX].ctrl,
                    ((uint32_t)GPIO_FUNC_UART << IO_BANK0_GPIO0_CTRL_FUNCSEL_LSB) |
                    ((uint32_t)GPIO_OVERRIDE_INVERT << IO_BANK0_GPIO0_CTRL_OUTOVER_LSB),
                    IO_BANK0_GPIO0_CTRL_FUNCSEL_BITS | IO_BANK0_GPIO0_CTRL_OUTOVER_BITS);

    gpio_init(PIN_KLINE_RX);
    gpio_disable_pulls(PIN_KLINE_RX);
    gpio_set_function(PIN_KLINE_RX, GPIO_FUNC_UART);

    gpio_init(PIN_ONBOARD_LED);
    gpio_put(PIN_ONBOARD_LED, 0u);
    gpio_set_dir(PIN_ONBOARD_LED, GPIO_OUT);

    gpio_init(PIN_STATUS_LED);
    gpio_put(PIN_STATUS_LED, 0u);
    gpio_set_dir(PIN_STATUS_LED, GPIO_OUT);

    gpio_init(PIN_TX_LED);
    gpio_put(PIN_TX_LED, 0u);
    gpio_set_dir(PIN_TX_LED, GPIO_OUT);

    gpio_init(PIN_RX_LED);
    gpio_put(PIN_RX_LED, 0u);
    gpio_set_dir(PIN_RX_LED, GPIO_OUT);
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
        service_activity_leds();
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
