cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(panda_breath)

# Copy build artifacts to a predictable location after build
add_custom_target(copy_build_artifacts ALL
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_SOURCE_DIR}/components/klipper/klipper/out
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_BINARY_DIR}/panda_breath.bin
        ${CMAKE_SOURCE_DIR}/components/klipper/klipper/out/panda_breath.bin
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_BINARY_DIR}/panda_breath.elf
        ${CMAKE_SOURCE_DIR}/components/klipper/klipper/out/panda_breath.elf
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_BINARY_DIR}/esp-idf/klipper/compile_time_request.c
        ${CMAKE_SOURCE_DIR}/components/klipper/klipper/out/compile_time_request.c
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_BINARY_DIR}/esp-idf/klipper/compile_time_request.txt
        ${CMAKE_SOURCE_DIR}/components/klipper/klipper/out/compile_time_request.txt
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_BINARY_DIR}/esp-idf/klipper/klipper.dict
        ${CMAKE_SOURCE_DIR}/components/klipper/klipper/out/klipper.dict
    COMMENT "Copying build artifacts to out/"
    VERBATIM
)

add_dependencies(copy_build_artifacts panda_breath.elf)
