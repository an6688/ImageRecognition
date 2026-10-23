#pragma once
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iosfwd>
#include <optional>
#include <string>
#include <vector>

namespace astro {
struct Frame {
    std::size_t index = 0;
    std::filesystem::path path;
    std::size_t width = 0, height = 0;
    unsigned bit_depth = 0;
    // Row-major, one grayscale sample per pixel, range [0, 2^bit_depth-1].
    std::vector<std::uint16_t> pixels;
};
struct Acquisition {
    std::size_t index = 0;
    std::filesystem::path path;
    std::optional<Frame> frame;
    std::string error;
    double decode_ms = 0;
};
class ImageSource {
public:
    virtual ~ImageSource() = default;
    // nullopt means exhaustion; a populated item without a frame means failure.
    virtual std::optional<Acquisition> next() = 0;
};
class FileImageSource final : public ImageSource {
public:
    explicit FileImageSource(const std::filesystem::path& directory);
    std::optional<Acquisition> next() override;
private:
    std::vector<std::filesystem::path> paths_;
    std::size_t cursor_ = 0;
};
struct StarMeasurement {
    double x, y; // Stored-raster pixel coordinates; no EXIF rotation.
    double major_sigma, minor_sigma, angle_degrees, elongation;
    double peak_contrast;
    bool elongated;
};
struct Quality {
    std::vector<StarMeasurement> stars;
    std::size_t peaks = 0, rejected = 0, examined = 0;
    bool coverage_limited = false;
    double median_elongation = 0, elongated_fraction = 0;
    std::string decision = "insufficient_evidence";
    std::string reason = "Fewer than 8 usable candidates";
};
// Provisional demo thresholds, fixed before evaluating the user's photos.
inline constexpr double elongation_threshold = 1.7;
inline constexpr double review_fraction = 0.4;
inline constexpr std::size_t minimum_stars = 8;
struct Analysis {
    std::size_t width, height;
    double mean_brightness;
    Quality quality;
};
// Requires a validated Frame; analyze() performs validation before calling this.
Quality measure_elongation(const Frame& frame, std::size_t peak_limit = 0);
Analysis analyze(const Frame& frame, std::size_t peak_limit = 0);
struct Summary { std::size_t succeeded = 0, failed = 0; };
// CSV stream errors are fatal; individual acquisition/analysis errors are rows.
Summary run(ImageSource& source, std::ostream& csv, std::ostream* candidates = nullptr, std::size_t peak_limit = 0);
}
