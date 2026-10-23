#include "astro/astro.hpp"
#include <chrono>
#include <iomanip>
#include <locale>
#include <ostream>
#include <sstream>
#include <stdexcept>

namespace astro {
namespace {
std::string quote(const std::string& value) {
    std::string result = "\"";
    for (char c : value) { if (c == '"') result += '"'; result += c; }
    return result + '"';
}
}
Summary run(ImageSource& source, std::ostream& csv, std::ostream* candidates, std::size_t peak_limit) {
    csv << "index,path,status,width,height,bit_depth,mean_brightness,decode_ms,analysis_ms,total_ms,error,review_decision,measured_candidates,peak_count,rejected_candidates,median_elongation,elongated_fraction,review_reason,analysis_version,coverage,examined_peaks,skipped_peaks,peak_limit\n";
    if (!csv) throw std::runtime_error("Cannot write CSV header");
    if (candidates) {
        *candidates << "index,path,candidate_id,x,y,major_sigma,minor_sigma,angle_degrees,elongation,peak_contrast,elongated\n";
        if (!*candidates) throw std::runtime_error("Cannot write candidate CSV header");
    }
    Summary summary;
    while (auto item = source.next()) {
        const auto start = std::chrono::steady_clock::now();
        std::optional<Analysis> result;
        if (item->frame) {
            try { result = analyze(*item->frame, peak_limit); }
            catch (const std::exception& error) { item->error = error.what(); }
        } else if (item->error.empty()) item->error = "Source returned no frame";
        const double analysis_ms = item->frame ? std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count() : 0.0;
        std::ostringstream row;
        row.imbue(std::locale::classic());
        row << std::fixed << std::setprecision(6) << item->index << ',' << quote(item->path.generic_u8string()) << ',';
        if (result) {
            ++summary.succeeded;
            row << "ok," << result->width << ',' << result->height << ',' << item->frame->bit_depth << ',' << result->mean_brightness;
        } else { ++summary.failed; row << "error,,,,"; }
        row << ',' << item->decode_ms << ',' << analysis_ms << ',' << item->decode_ms + analysis_ms << ',' << quote(item->error);
        if (result) {
            const auto& q = result->quality;
            row << ',' << q.decision << ',' << q.stars.size() << ',' << q.peaks << ',' << q.rejected << ',';
            if (!q.stars.empty()) row << q.median_elongation;
            row << ',';
            if (!q.stars.empty()) row << q.elongated_fraction;
            row << ',' << quote(q.reason) << ",elongation-v2," << (q.coverage_limited ? "limited" : "all_detected_peaks")
                << ',' << q.examined << ',' << q.peaks - q.examined << ',' << peak_limit << '\n';
            if (candidates) {
                for (std::size_t i = 0; i < q.stars.size(); ++i) {
                    const auto& star = q.stars[i];
                    std::ostringstream detail;
                    detail.imbue(std::locale::classic());
                    detail << std::fixed << std::setprecision(6) << item->index << ',' << quote(item->path.generic_u8string())
                        << ',' << i << ',' << star.x << ',' << star.y << ',' << star.major_sigma << ',' << star.minor_sigma
                        << ',' << star.angle_degrees << ',' << star.elongation << ',' << star.peak_contrast << ',' << star.elongated << '\n';
                    *candidates << detail.str();
                    if (!*candidates) throw std::runtime_error("Cannot write candidate CSV row");
                }
            }
        } else row << ",not_analyzed,0,0,0,,,\"Image analysis unavailable\",elongation-v2,not_analyzed,0,0," << peak_limit << '\n';
        csv << row.str();
        if (!csv) throw std::runtime_error("Cannot write CSV row");
    }
    csv.flush();
    if (!csv) throw std::runtime_error("Cannot flush CSV");
    if (candidates) { candidates->flush(); if (!*candidates) throw std::runtime_error("Cannot flush candidate CSV"); }
    return summary;
}
}
