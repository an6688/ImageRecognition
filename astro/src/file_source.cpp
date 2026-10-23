#include "astro/astro.hpp"
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <chrono>
#include <cctype>
#include <fstream>
#include <iterator>
#include <stdexcept>

namespace astro {
FileImageSource::FileImageSource(const std::filesystem::path& directory) {
    if (!std::filesystem::is_directory(directory))
        throw std::invalid_argument("Input must be an accessible directory");
    for (const auto& entry : std::filesystem::directory_iterator(directory)) {
        if (!entry.is_regular_file()) continue;
        auto ext = entry.path().extension().u8string();
        std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        if (ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".tif" || ext == ".tiff")
            paths_.push_back(entry.path());
    }
    std::sort(paths_.begin(), paths_.end(), [](const auto& a, const auto& b) { return a.generic_u8string() < b.generic_u8string(); });
}
std::optional<Acquisition> FileImageSource::next() {
    if (cursor_ == paths_.size()) return std::nullopt;
    Acquisition item;
    item.index = cursor_;
    item.path = paths_[cursor_++];
    const auto start = std::chrono::steady_clock::now();
    try {
        // Native filesystem paths allow Unicode Windows filenames; imread does not.
        std::ifstream file(item.path, std::ios::binary);
        if (!file) throw std::runtime_error("Cannot open image");
        std::vector<unsigned char> bytes((std::istreambuf_iterator<char>(file)), {});
        if (file.bad()) throw std::runtime_error("Cannot read image");
        if (bytes.empty()) throw std::runtime_error("Empty image file");
        auto decoded = cv::imdecode(bytes, cv::IMREAD_UNCHANGED);
        if (decoded.empty()) throw std::runtime_error("Image decoder rejected file");
        if (decoded.depth() != CV_8U && decoded.depth() != CV_16U)
            throw std::runtime_error("Only unsigned 8/16-bit images are supported");
        cv::Mat gray;
        if (decoded.channels() == 1) gray = decoded;
        else if (decoded.channels() == 3) cv::cvtColor(decoded, gray, cv::COLOR_BGR2GRAY);
        else if (decoded.channels() == 4) cv::cvtColor(decoded, gray, cv::COLOR_BGRA2GRAY);
        else throw std::runtime_error("Unsupported channel count");
        Frame frame;
        frame.index = item.index; frame.path = item.path;
        frame.width = static_cast<std::size_t>(gray.cols);
        frame.height = static_cast<std::size_t>(gray.rows);
        frame.bit_depth = gray.depth() == CV_8U ? 8 : 16;
        frame.pixels.resize(frame.width * frame.height);
        for (int y = 0; y < gray.rows; ++y)
            for (int x = 0; x < gray.cols; ++x)
                frame.pixels[static_cast<std::size_t>(y) * frame.width + x] =
                    frame.bit_depth == 8 ? gray.at<std::uint8_t>(y, x) : gray.at<std::uint16_t>(y, x);
        item.frame = std::move(frame);
    } catch (const std::exception& error) {
        item.error = error.what();
    }
    item.decode_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
    return item;
}
}
