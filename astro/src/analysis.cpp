#include "astro/astro.hpp"
#include <limits>
#include <stdexcept>

namespace astro {
Analysis analyze(const Frame& frame, std::size_t peak_limit) {
    if (!frame.width || !frame.height ||
        frame.width > static_cast<std::size_t>(std::numeric_limits<int>::max() - 64) ||
        frame.height > static_cast<std::size_t>(std::numeric_limits<int>::max() - 64) ||
        frame.width > std::numeric_limits<std::size_t>::max() / frame.height ||
        frame.pixels.size() != frame.width * frame.height ||
        (frame.bit_depth != 8 && frame.bit_depth != 16))
        throw std::invalid_argument("Invalid grayscale frame layout or depth");
    const double maximum = frame.bit_depth == 8 ? 255.0 : 65535.0;
    double sum = 0;
    for (auto pixel : frame.pixels) {
        if (pixel > maximum) throw std::invalid_argument("Pixel exceeds frame bit depth");
        sum += pixel;
    }
    return {frame.width, frame.height, sum / frame.pixels.size() / maximum, measure_elongation(frame, peak_limit)};
}
}
