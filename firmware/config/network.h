#pragma once

// Keep Wi-Fi credentials and the Agent address out of the repository. Copy
// network_secrets.h.example to network_secrets.h for a local device build.
#if __has_include("network_secrets.h")
#include "network_secrets.h"
#endif

#ifndef MIMI_WIFI_SSID
#define MIMI_WIFI_SSID ""
#endif

#ifndef MIMI_WIFI_PASSWORD
#define MIMI_WIFI_PASSWORD ""
#endif

#ifndef MIMI_AGENT_HOST
#define MIMI_AGENT_HOST ""
#endif

#ifndef MIMI_AGENT_PORT
#define MIMI_AGENT_PORT 8765
#endif

#ifndef MIMI_AGENT_PATH
#define MIMI_AGENT_PATH "/"
#endif

#ifndef MIMI_DEVICE_ID
#define MIMI_DEVICE_ID "mimi-c3"
#endif

namespace mimi {
namespace network_config {

constexpr const char* WIFI_SSID = MIMI_WIFI_SSID;
constexpr const char* WIFI_PASSWORD = MIMI_WIFI_PASSWORD;
constexpr const char* AGENT_HOST = MIMI_AGENT_HOST;
constexpr uint16_t AGENT_PORT = MIMI_AGENT_PORT;
constexpr const char* AGENT_PATH = MIMI_AGENT_PATH;
constexpr const char* DEVICE_ID = MIMI_DEVICE_ID;

}  // namespace network_config
}  // namespace mimi
