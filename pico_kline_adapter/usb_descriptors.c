// SPDX-License-Identifier: MIT
/*
 * Copyright (c) 2021 Alvaro Fernandez Rojas <noltari@gmail.com>
 * Copyright (c) 2020 Raspberry Pi (Trading) Ltd.
 * Copyright (c) 2019 Ha Thach (tinyusb.org)
 *
 * Adapted under the MIT License for one CDC ACM interface and a stable RP2040
 * flash-derived serial number.
 */

#include <stddef.h>
#include <stdint.h>

#include "hardware/flash.h"
#include "tusb.h"

#define USB_VID 0x2e8au
#define USB_PID 0x000au
#define USB_BCD 0x0100u

enum {
    ITF_NUM_CDC = 0,
    ITF_NUM_CDC_DATA,
    ITF_NUM_TOTAL,
};

enum {
    STR_ID_LANGID = 0,
    STR_ID_MANUFACTURER,
    STR_ID_PRODUCT,
    STR_ID_SERIAL,
    STR_ID_CDC,
};

#define EPNUM_CDC_NOTIF 0x81u
#define EPNUM_CDC_OUT 0x02u
#define EPNUM_CDC_IN 0x82u
#define CONFIG_TOTAL_LEN (TUD_CONFIG_DESC_LEN + TUD_CDC_DESC_LEN)

static tusb_desc_device_t const device_descriptor = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = TUSB_CLASS_MISC,
    .bDeviceSubClass = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = USB_VID,
    .idProduct = USB_PID,
    .bcdDevice = USB_BCD,
    .iManufacturer = STR_ID_MANUFACTURER,
    .iProduct = STR_ID_PRODUCT,
    .iSerialNumber = STR_ID_SERIAL,
    .bNumConfigurations = 1,
};

static uint8_t const configuration_descriptor[] = {
    TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, 0, CONFIG_TOTAL_LEN, 0, 100),
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC, STR_ID_CDC, EPNUM_CDC_NOTIF, 8,
                       EPNUM_CDC_OUT, EPNUM_CDC_IN, 64),
};

static char usb_serial[17] = "0000000000000000";
static char const *const string_descriptors[] = {
    [STR_ID_MANUFACTURER] = "Ras SH7055 project",
    [STR_ID_PRODUCT] = "Pico AD310 K-Line",
    [STR_ID_SERIAL] = usb_serial,
    [STR_ID_CDC] = "Raw K-Line serial",
};

void usb_serial_number_init(void) {
    static char const hex[] = "0123456789ABCDEF";
    uint8_t id[8];

    flash_get_unique_id(id);
    for (uint32_t i = 0u; i < sizeof(id); ++i) {
        usb_serial[i * 2u] = hex[id[i] >> 4u];
        usb_serial[i * 2u + 1u] = hex[id[i] & 0x0fu];
    }
    usb_serial[16] = '\0';
}

uint8_t const *tud_descriptor_device_cb(void) {
    return (uint8_t const *)&device_descriptor;
}

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
    (void)index;
    return configuration_descriptor;
}

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    (void)langid;
    static uint16_t descriptor[32];
    uint8_t length = 0u;

    if (index == STR_ID_LANGID) {
        descriptor[1] = 0x0409;
        length = 1u;
    } else {
        size_t count = sizeof(string_descriptors) /
                       sizeof(string_descriptors[0]);
        if (index >= count || string_descriptors[index] == NULL) {
            return NULL;
        }

        char const *text = string_descriptors[index];
        while (text[length] != '\0' && length < 31u) {
            descriptor[1u + length] = (uint8_t)text[length];
            length++;
        }
    }

    descriptor[0] = (uint16_t)((TUSB_DESC_STRING << 8u) |
                               (2u * length + 2u));
    return descriptor;
}
