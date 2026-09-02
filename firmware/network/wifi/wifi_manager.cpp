#include "wifi_manager.h"

namespace mimi {
namespace network {

bool WifiManager::begin(const char* ssid, const char* password) {
  ssid_ = ssid == nullptr ? "" : ssid;
  password_ = password == nullptr ? "" : password;
  configured_ = !ssid_.isEmpty();
  if (!configured_) {
    Serial.println("WiFi disabled; configure firmware/config/network_secrets.h");
    return false;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid_.c_str(), password_.c_str());
  next_retry_ms_ = millis() + RETRY_INTERVAL_MS;
  Serial.printf("WiFi connecting to %s\n", ssid_.c_str());
  return true;
}

void WifiManager::loop() {
  if (!configured_ || connected()) {
    return;
  }

  const uint32_t now = millis();
  if (static_cast<int32_t>(now - next_retry_ms_) >= 0) {
    WiFi.disconnect();
    WiFi.begin(ssid_.c_str(), password_.c_str());
    next_retry_ms_ = now + RETRY_INTERVAL_MS;
    Serial.println("WiFi retrying");
  }
}

bool WifiManager::connected() const { return configured_ && WiFi.status() == WL_CONNECTED; }

}  // namespace network
}  // namespace mimi
