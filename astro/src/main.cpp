#include "astro/astro.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <limits>

int launch(const std::filesystem::path& input, const std::filesystem::path& output, const std::filesystem::path& details, std::size_t peak_limit) {
    try {
        astro::FileImageSource source(input);
        if (output.extension() != ".csv") throw std::invalid_argument("Output must have .csv extension");
        // Never truncate an existing result or accidentally overwrite an input image.
        if (std::filesystem::exists(output)) throw std::invalid_argument("Output already exists; choose a new CSV path");
        if (!details.empty() && (details.extension() != ".csv" || std::filesystem::exists(details) ||
            std::filesystem::weakly_canonical(details) == std::filesystem::weakly_canonical(output)))
            throw std::invalid_argument("Candidate output must be a distinct, new .csv path");
        std::ofstream csv(output, std::ios::binary);
        if (!csv) throw std::runtime_error("Cannot create CSV output");
        std::ofstream candidates;
        if (!details.empty()) {
            // Also catches Windows case aliases of the primary path after creation.
            if (std::filesystem::exists(details)) throw std::invalid_argument("Candidate output already exists");
            candidates.open(details, std::ios::binary);
            if (!candidates) throw std::runtime_error("Cannot create candidate CSV output");
        }
        const auto summary = astro::run(source, csv, details.empty() ? nullptr : &candidates, peak_limit);
        std::cout << summary.succeeded << " succeeded, " << summary.failed << " failed\n";
        if (!summary.succeeded && !summary.failed) { std::cerr << "No supported images found\n"; return 2; }
        return summary.failed ? 1 : 0;
    } catch (const std::exception& error) {
        std::cerr << "astro_analyze: " << error.what() << '\n'; return 2;
    }
}
#ifdef _WIN32
int wmain(int argc, wchar_t* argv[]) {
#else
int main(int argc, char* argv[]) {
#endif
    std::size_t peak_limit = 0;
    if (argc >= 5 && std::filesystem::path(argv[argc - 2]) == "--peak-limit") {
        try {
            const auto value = std::filesystem::path(argv[argc - 1]).u8string();
            if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
                throw std::invalid_argument("Peak limit must be a nonnegative integer (0 = all)");
            const auto parsed = std::stoull(value);
            if (parsed > std::numeric_limits<std::size_t>::max()) throw std::out_of_range("Peak limit too large");
            peak_limit = static_cast<std::size_t>(parsed);
        } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
        argc -= 2;
    }
    if (argc != 3 && argc != 4) {
        std::cerr << "Usage: astro_analyze <input-directory> <new-output.csv> [new-candidates.csv] [--peak-limit N]\n";
        return 2;
    }
    return launch(argv[1], argv[2], argc == 4 ? std::filesystem::path(argv[3]) : std::filesystem::path{}, peak_limit);
}
