#include "astro/astro.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <random>
#include <stdexcept>

void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
astro::Frame field(unsigned depth = 8, bool gradient = false) {
    astro::Frame frame;
    frame.width = 512; frame.height = 384; frame.bit_depth = depth;
    const double maximum = depth == 8 ? 255 : 65535;
    std::mt19937 generator(407);
    frame.pixels.resize(frame.width * frame.height);
    for (std::size_t y = 0; y < frame.height; ++y) for (std::size_t x = 0; x < frame.width; ++x) {
        double level = .08 + (gradient ? .12 * x / frame.width + .05 * y / frame.height : 0);
        level += (static_cast<int>(generator() % 5) - 2) / 1000.0;
        frame.pixels[y * frame.width + x] = static_cast<std::uint16_t>(std::round(level * maximum));
    }
    return frame;
}
void star(astro::Frame& frame, int cx, int cy, double a, double b, double angle = 0, double amplitude = .5) {
    const double maximum = frame.bit_depth == 8 ? 255 : 65535;
    for (int y = std::max(0, cy - 18); y < std::min(static_cast<int>(frame.height), cy + 19); ++y)
        for (int x = std::max(0, cx - 18); x < std::min(static_cast<int>(frame.width), cx + 19); ++x) {
            double u = (x - cx) * std::cos(angle) + (y - cy) * std::sin(angle);
            double v = -(x - cx) * std::sin(angle) + (y - cy) * std::cos(angle);
            auto& pixel = frame.pixels[static_cast<std::size_t>(y) * frame.width + x];
            pixel = static_cast<std::uint16_t>(std::min(maximum, std::round(pixel + maximum * amplitude * std::exp(-.5 * (u*u/(a*a) + v*v/(b*b))))));
        }
}
astro::Quality grid(double a, double b, double angle = 0, unsigned depth = 8, bool gradient = false) {
    auto frame = field(depth, gradient);
    for (int y = 64; y <= 320; y += 64) for (int x = 64; x <= 448; x += 64) star(frame, x, y, a, b, angle);
    return astro::analyze(frame).quality;
}
int main() {
    try {
        const auto round = grid(1.5, 1.5);
        require(round.stars.size() == 35, "Recover isolated round sources");
        require(round.decision == "no_elongation_flag" && round.median_elongation < 1.1, "Round field not flagged");
        const auto stretched = grid(3, 1.25);
        require(stretched.stars.size() == 35 && stretched.decision == "review_suggested", "Elongated field flagged");
        require(std::abs(stretched.median_elongation - 2.4) < .2, "Known axis ratio recovered");
        const auto rotated = grid(3, 1.25, .7853981633974483);
        require(rotated.decision == "review_suggested", "Rotation preserves review decision");
        require(std::abs(rotated.stars[0].angle_degrees - 45) < 3, "Orientation recovered");
        const auto deep = grid(3, 1.25, 0, 16, true);
        require(deep.decision == "review_suggested" && deep.stars.size() == 35, "16-bit gradient field");
        require(grid(1.5, 1.5, 0, 8, true).decision == "no_elongation_flag", "Round stars on gradient");
        require(astro::analyze(field()).quality.decision == "insufficient_evidence", "Noise-only field insufficient");
        require(astro::analyze(field(16, true)).quality.stars.empty(), "Gradient-only field has no candidates");
        auto sparse = field();
        for (int x = 64; x <= 256; x += 64) star(sparse, x, 64, 3, 1.25);
        auto sparse_result = astro::analyze(sparse).quality;
        require(sparse_result.stars.size() == 4 && sparse_result.decision == "insufficient_evidence", "Too few candidates never certify quality");
        auto defects = field();
        for (int x = 64; x <= 448; x += 64) {
            star(defects, x, 64, 1.5, 1.5, 0, 1.2); // Saturated.
            defects.pixels[192 * defects.width + x] = 200; // Hot pixel.
        }
        for (int x = 20; x < 480; ++x) defects.pixels[300 * defects.width + x] = 180;
        require(astro::analyze(defects).quality.stars.empty(), "Saturation, hot pixels and long line excluded");
        auto mixed = field();
        int count = 0;
        for (int y = 64; y <= 320; y += 64) for (int x = 64; x <= 448; x += 64) {
            bool elongated = count++ < 14;
            star(mixed, x, y, elongated ? 3 : 1.5, elongated ? 1.25 : 1.5);
        }
        auto mix_result = astro::analyze(mixed).quality;
        require(mix_result.decision == "review_suggested" && std::abs(mix_result.elongated_fraction - .4) < 1e-10, "40 percent review boundary");
        auto many = field(); many.width = many.height = 1024; many.pixels.assign(1024 * 1024, 20);
        for (int y = 16; y < 1000; y += 16) for (int x = 16; x < 1000; x += 16) many.pixels[y * 1024 + x] = 150;
        auto all = astro::analyze(many).quality;
        auto capped = astro::analyze(many, 2000).quality;
        require(all.peaks > 2000 && all.examined == all.peaks && !all.coverage_limited, "Default examines all peaks");
        require(capped.examined == 2000 && capped.coverage_limited, "Optional cap reports limited coverage");
        auto subset = astro::analyze(mixed, 20).quality;
        require(subset.coverage_limited && subset.stars.size() >= 8 && subset.decision != "insufficient_evidence", "Coverage does not erase measured shape result");
        require(subset.examined == subset.rejected + subset.stars.size(), "Every examined peak is accounted for");
        std::cout << "Quality tests passed: round/elongated/rotated/gradient/16-bit/sparse/noise/defects/mixed/capped fields\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
