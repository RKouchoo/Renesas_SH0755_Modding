cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(pico_ad310_kline_bridge C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(pico_ad310_kline_bridge
    main.c
    usb_descriptors.c
)

target_include_directories(pico_ad310_kline_bridge PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_compile_options(pico_ad310_kline_bridge PRIVATE
    -Wall
    -Wextra
    -Werror
    -Wshadow
)

target_link_libraries(pico_ad310_kline_bridge
    hardware_flash
    hardware_gpio
    hardware_uart
    hardware_watchdog
    pico_stdlib
    tinyusb_device
)

pico_enable_stdio_usb(pico_ad310_kline_bridge 0)
pico_enable_stdio_uart(pico_ad310_kline_bridge 0)

pico_set_program_name(pico_ad310_kline_bridge "Pico AD310 K-Line Bridge")
pico_set_program_version(pico_ad310_kline_bridge "1.0.0")
pico_set_program_description(pico_ad310_kline_bridge
    "Raw USB CDC to inverted AD310 K-line bridge")

pico_add_extra_outputs(pico_ad310_kline_bridge)
