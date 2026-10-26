#include "astro/astro.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <queue>
#include <vector>

namespace astro {
namespace {
constexpr int radius = 10, side = 21, tile = 64;
constexpr double pi = 3.14159265358979323846;
double median(std::vector<double> values) {
    auto mid = values.begin() + values.size() / 2;
    std::nth_element(values.begin(), mid, values.end());
    double answer = *mid;
    if (values.size() % 2 == 0) answer = (answer + *std::max_element(values.begin(), mid)) / 2;
    return answer;
}
struct Background { double level, noise; };
Background background(const std::vector<double>& values, double quantization) {
    const double level = median(values);
    std::vector<double> deviations;
    deviations.reserve(values.size());
    for (double value : values) deviations.push_back(std::abs(value - level));
    return {level, std::max(1.4826 * median(std::move(deviations)), quantization)};
}
struct Peak { int x, y; double contrast; };
struct Brighter { bool operator()(const Peak& a, const Peak& b) const {
    return a.contrast > b.contrast;
} };
}
Quality measure_elongation(const Frame& frame, std::size_t peak_limit) {
    Quality result;
    if (frame.width < side || frame.height < side) return result;
    const double maximum = frame.bit_depth == 8 ? 255.0 : 65535.0;
    // Pixel coordinates are bounded by the decoder's signed-int dimensions.
    const int width = static_cast<int>(frame.width), height = static_cast<int>(frame.height);
    auto at = [&](int x, int y) { return frame.pixels[static_cast<std::size_t>(y) * frame.width + x] / maximum; };
    const int nx = (width + tile - 1) / tile, ny = (height + tile - 1) / tile;
    std::vector<Background> sky;
    sky.reserve(static_cast<std::size_t>(nx) * ny);
    for (int ty = 0; ty < ny; ++ty) for (int tx = 0; tx < nx; ++tx) {
        std::vector<double> samples;
        for (int y = ty * tile; y < std::min((ty + 1) * tile, height); y += 2)
            for (int x = tx * tile; x < std::min((tx + 1) * tile, width); x += 2)
                samples.push_back(at(x, y));
        sky.push_back(background(samples, 1.0 / maximum));
    }
    std::priority_queue<Peak, std::vector<Peak>, Brighter> strongest;
    for (int y = radius; y < height - radius; ++y) for (int x = radius; x < width - radius; ++x) {
        const auto& bg = sky[static_cast<std::size_t>(y / tile) * nx + x / tile];
        const double value = at(x, y), contrast = value - bg.level;
        if (contrast < std::max(5 * bg.noise, 2.0 / 255.0)) continue;
        bool is_peak = true;
        for (int dy = -2; dy <= 2 && is_peak; ++dy) for (int dx = -2; dx <= 2; ++dx) {
            if (dx == 0 && dy == 0) continue;
            const double other = at(x + dx, y + dy);
            // Resolve equal plateaus deterministically to one local representative.
            if (other > value || (other == value && (dy < 0 || (dy == 0 && dx < 0)))) { is_peak = false; break; }
        }
        if (!is_peak) continue;
        ++result.peaks;
        strongest.push({x, y, contrast});
        if (peak_limit && strongest.size() > peak_limit) strongest.pop();
    }
    std::vector<Peak> peaks;
    while (!strongest.empty()) { peaks.push_back(strongest.top()); strongest.pop(); }
    result.examined = peaks.size();
    result.coverage_limited = result.examined < result.peaks;
    std::sort(peaks.begin(), peaks.end(), [](const Peak& a, const Peak& b) {
        if (a.contrast != b.contrast) return a.contrast > b.contrast;
        return a.y != b.y ? a.y < b.y : a.x < b.x;
    });
    // Accepted stars are bucketed in 2*radius cells, so the overlap test visits at most 9 cells instead of every star.
    const int cell = 2 * radius, cells_x = (width + cell - 1) / cell, cells_y = (height + cell - 1) / cell;
    std::vector<std::vector<std::size_t>> buckets(static_cast<std::size_t>(cells_x) * cells_y);
    auto bucket_of = [&](int x, int y) { return static_cast<std::size_t>(y / cell) * cells_x + x / cell; };
    for (const auto& peak : peaks) {
        bool overlap = false;
        const int bx = peak.x / cell, by = peak.y / cell;
        for (int gy = std::max(0, by - 1); gy <= std::min(cells_y - 1, by + 1) && !overlap; ++gy)
            for (int gx = std::max(0, bx - 1); gx <= std::min(cells_x - 1, bx + 1) && !overlap; ++gx)
                for (std::size_t i : buckets[static_cast<std::size_t>(gy) * cells_x + gx])
                    if (std::hypot(result.stars[i].x - peak.x, result.stars[i].y - peak.y) < 2 * radius) { overlap = true; break; }
        if (overlap) { ++result.rejected; continue; }
        std::vector<double> ring;
        for (int dy = -radius; dy <= radius; ++dy) for (int dx = -radius; dx <= radius; ++dx)
            if (std::max(std::abs(dx), std::abs(dy)) >= 8) ring.push_back(at(peak.x + dx, peak.y + dy));
        const auto bg = background(ring, 1.0 / maximum);
        const double contrast = at(peak.x, peak.y) - bg.level;
        if (contrast < std::max(5 * bg.noise, 2.0 / 255.0)) { ++result.rejected; continue; }
        const double threshold = bg.level + std::max(3 * bg.noise, .1 * contrast);
        // Flood only the central source; unrelated nearby pixels do not enter moments.
        std::array<bool, side * side> seen{};
        std::vector<int> component{radius * side + radius};
        seen[component[0]] = true;
        double mass = 0, sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
        bool clipped = false, saturated = false;
        for (std::size_t i = 0; i < component.size(); ++i) {
            const int px = component[i] % side, py = component[i] / side;
            const int dx = px - radius, dy = py - radius;
            const double value = at(peak.x + dx, peak.y + dy), weight = value - bg.level;
            saturated = saturated || value >= .98;
            clipped = clipped || px == 0 || py == 0 || px == side - 1 || py == side - 1;
            mass += weight; sx += weight * dx; sy += weight * dy;
            sxx += weight * dx * dx; syy += weight * dy * dy; sxy += weight * dx * dy;
            for (int oy = -1; oy <= 1; ++oy) for (int ox = -1; ox <= 1; ++ox) {
                const int qx = px + ox, qy = py + oy;
                if (qx < 0 || qy < 0 || qx >= side || qy >= side) continue;
                const int index = qy * side + qx;
                if (!seen[index] && at(peak.x + qx - radius, peak.y + qy - radius) > threshold) {
                    seen[index] = true; component.push_back(index);
                }
            }
        }
        if (clipped || saturated || component.size() < 6 || mass <= 0) { ++result.rejected; continue; }
        const double cx = sx / mass, cy = sy / mass;
        const double xx = sxx / mass - cx * cx, yy = syy / mass - cy * cy, xy = sxy / mass - cx * cy;
        const double delta = std::hypot(xx - yy, 2 * xy);
        const double major = std::sqrt(std::max(0.0, (xx + yy + delta) / 2));
        const double minor = std::sqrt(std::max(0.0, (xx + yy - delta) / 2));
        if (minor < .65 || major > 5 || std::hypot(cx, cy) > 3 || major / minor > 6) { ++result.rejected; continue; }
        const double ratio = major / minor;
        result.stars.push_back({peak.x + cx, peak.y + cy, major, minor,
            .5 * std::atan2(2 * xy, xx - yy) * 180 / pi, ratio, contrast, ratio >= elongation_threshold});
        const auto& added = result.stars.back();
        buckets[bucket_of(static_cast<int>(added.x), static_cast<int>(added.y))].push_back(result.stars.size() - 1);
    }
    if (!result.stars.empty()) {
        std::vector<double> ratios;
        std::size_t elongated = 0;
        for (const auto& star : result.stars) { ratios.push_back(star.elongation); elongated += star.elongated ? 1 : 0; }
        result.median_elongation = median(std::move(ratios));
        result.elongated_fraction = static_cast<double>(elongated) / result.stars.size();
    }
    if (result.stars.size() >= minimum_stars) {
        const bool flag = result.elongated_fraction >= review_fraction;
        result.decision = flag ? "review_suggested" : "no_elongation_flag";
        result.reason = flag ? "At least 40% of usable candidates have axis ratio >= 1.7" :
            "Fewer than 40% of usable candidates have axis ratio >= 1.7; not a quality certification";
    }
    if (result.coverage_limited) result.reason += "; shape result applies only to the brightest examined subset";
    return result;
}
}
