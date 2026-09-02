#pragma once

namespace mimi {
namespace motion_config {

// Physical installation calibration for the current MPU6050-V1 breakout.
// With the module mounted in the present Mimi prototype, its raw pitch sign
// is opposite to Mimi's front/back convention. Set this to +1 after rotating
// the module so the two coordinate systems point in the same direction.
constexpr int MPU6050_PITCH_SIGN = -1;

// The current left/right orientation is already correct.
constexpr int MPU6050_ROLL_SIGN = 1;

}  // namespace motion_config
}  // namespace mimi
