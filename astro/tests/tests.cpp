#include "astro/astro.hpp"
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>

void check(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class F> void throws(F action) {
    bool caught = false;
    try { action(); } catch (const std::exception&) { caught = true; }
    check(caught, "Expected an exception");
}
void write_image(const std::filesystem::path& path, const cv::Mat& pixels) {
    std::vector<unsigned char> bytes;
    check(cv::imencode(path.extension().string(), pixels, bytes), "Encode fixture");
    std::ofstream file(path, std::ios::binary);
    file.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    check(static_cast<bool>(file), "Write fixture");
}
struct Temp {
    std::filesystem::path path = std::filesystem::temp_directory_path() /
        ("astro-tests-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    Temp() { std::filesystem::create_directory(path); }
    ~Temp() { std::error_code ec; std::filesystem::remove_all(path, ec); }
};
class FakeSource : public astro::ImageSource {
    int index_ = 0;
public:
    std::optional<astro::Acquisition> next() override {
        if (index_++ == 2) return std::nullopt;
        astro::Acquisition item;
        item.path = "comma,quote\"newline\n.png";
        item.index = index_;
        item.frame = astro::Frame{};
        if (index_ == 2) { item.frame->width = item.frame->height = 1; item.frame->bit_depth = 8; item.frame->pixels = {255}; }
        return item;
    }
};
int main() {
    try {
        astro::Frame f; f.width = 2; f.height = 1; f.bit_depth = 8; f.pixels = {0, 255};
        check(std::abs(astro::analyze(f).mean_brightness - .5) < 1e-12, "8-bit normalization");
        f.bit_depth = 16; f.pixels = {0, 65535};
        check(std::abs(astro::analyze(f).mean_brightness - .5) < 1e-12, "16-bit normalization");
        f.pixels.pop_back(); throws([&] { astro::analyze(f); });
        f.pixels = {0, 256}; f.bit_depth = 8; throws([&] { astro::analyze(f); });
        f.width = 0; throws([&] { astro::analyze(f); });
        Temp temp;
        throws([&] { astro::FileImageSource missing(temp.path / "missing"); });
        astro::FileImageSource empty(temp.path); check(!empty.next(), "Empty folder");
        write_image(temp.path / "01.png", cv::Mat(2, 3, CV_8UC3, cv::Scalar(0, 0, 255)));
        std::ofstream(temp.path / "02.png") << "corrupt";
        write_image(temp.path / "03.JPG", cv::Mat(3, 4, CV_8UC1, cv::Scalar(128)));
        write_image(temp.path / "04.tiff", cv::Mat(2, 5, CV_16UC1, cv::Scalar(32768)));
        write_image(temp.path / std::filesystem::u8path("05-\xc3\xa9.png"), cv::Mat(1, 1, CV_16UC1, cv::Scalar(65535)));
        write_image(temp.path / "06.tif", cv::Mat(1, 2, CV_8UC4, cv::Scalar(255, 255, 255, 0)));
        std::ofstream(temp.path / "07.jpeg");
        std::ofstream(temp.path / "ignored.txt") << "ignored";
        std::filesystem::create_directory(temp.path / "nested");
        write_image(temp.path / "nested" / "ignored.png", cv::Mat(1, 1, CV_8UC1, cv::Scalar(0)));
        astro::FileImageSource source(temp.path);
        auto first = source.next();
        check(first && first->frame && first->index == 0 && first->frame->width == 3, "Sorted dimensions");
        check(first->frame->pixels[0] == 76, "BGR grayscale conversion");
        check(first->decode_ms >= 0, "Decode timer");
        auto bad = source.next(); check(bad && !bad->frame && !bad->error.empty(), "Corrupt decode");
        auto jpeg = source.next(); check(jpeg && jpeg->frame && jpeg->frame->height == 3, "Continue after corrupt JPEG/PNG");
        check(std::abs(astro::analyze(*jpeg->frame).mean_brightness - 128.0 / 255) < .01, "JPEG brightness");
        auto tiff = source.next(); check(tiff && tiff->frame && tiff->frame->bit_depth == 16 && tiff->frame->pixels[0] == 32768, "16-bit TIFF");
        auto png16 = source.next(); check(png16 && png16->frame && png16->frame->pixels[0] == 65535, "16-bit PNG and Unicode path");
        auto rgba = source.next(); check(rgba && rgba->frame && rgba->frame->pixels[0] == 255, "Alpha ignored");
        auto zero = source.next(); check(zero && !zero->frame, "Empty image failure");
        check(!source.next() && !source.next(), "Stable exhaustion and nonrecursive filtering");
        astro::FileImageSource batch(temp.path); std::ostringstream csv;
        auto summary = astro::run(batch, csv);
        check(summary.succeeded == 5 && summary.failed == 2, "Batch counts");
        check(csv.str().find("mean_brightness,decode_ms,analysis_ms,total_ms,error") != std::string::npos, "CSV schema");
        check(csv.str().find(",error,,,,,") != std::string::npos, "Error row empty metrics");
        FakeSource fake; std::ostringstream quoted;
        summary = astro::run(fake, quoted);
        check(summary.failed == 1 && summary.succeeded == 1, "Invalid frame recovery");
        check(quoted.str().find("\"comma,quote\"\"newline\n.png\"") != std::string::npos, "CSV escaping");
        FakeSource sink_source; std::ostringstream broken; broken.setstate(std::ios::badbit);
        throws([&] { astro::run(sink_source, broken); });
        std::cout << "All focused Astro checks passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
