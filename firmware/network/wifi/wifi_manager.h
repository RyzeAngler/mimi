#pragma once

#include <Arduino.h>
#include <WiFi.h>

namespace mimi {
namespace network {

class WifiManager {
 public:
  bool begin(const char* ssid, const char* password);
  void loop();
  bool connected() const;

 private:
  static constexpr uint32_t RETRY_INTERVAL_MS = 10000;

  String ssid_;
  String password_;
  uint32_t next_retry_ms_ = 0;
  bool configured_ = false;
};

}  // namespace network
}  // namespace mimi
