cmake_minimum_required(VERSION 3.10)
project(Servidor_Seguranca CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Encontra a instalação do OpenCV (com módulos core, imgproc, videoio, objdetect, face)
find_package(OpenCV REQUIRED)

# Cria o executável do Servidor Edge
add_executable(Servidor_Seguranca 
    main.cpp 
    http_client.cpp
)

target_include_directories(Servidor_Seguranca PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${OpenCV_INCLUDE_DIRS}
)

target_link_libraries(Servidor_Seguranca PRIVATE 
    ${OpenCV_LIBS}
)

# No Windows, vincula a biblioteca de sockets (Winsock2)
if(WIN32)
    target_link_libraries(Servidor_Seguranca PRIVATE ws2_32)
endif()
