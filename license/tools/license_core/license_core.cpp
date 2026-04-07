/**
 * license_core.cpp
 * High-level API: generate_license() and verify_license().
 */

#include "include/license_core.h"
#include "license_io.h"
#include "rsa_utils.h"

#include <algorithm>
#include <cctype>
#include <cstring>
#include <ctime>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#if defined(__APPLE__)
#include <TargetConditionals.h>
#endif

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------
namespace {

// Parse an ISO8601 UTC timestamp ("YYYY-MM-DDTHH:MM:SSZ") into time_t.
// Returns -1 on parse failure.
time_t parse_iso8601(const std::string& ts)
{
    if (ts.empty()) return -1;
    struct tm t = {};
    // Try "YYYY-MM-DDTHH:MM:SSZ"
    if (sscanf(ts.c_str(), "%d-%d-%dT%d:%d:%dZ",
               &t.tm_year, &t.tm_mon, &t.tm_mday,
               &t.tm_hour, &t.tm_min, &t.tm_sec) == 6) {
        t.tm_year -= 1900;
        t.tm_mon  -= 1;
        t.tm_isdst = 0;
#ifdef _WIN32
        return _mkgmtime(&t);
#else
        return timegm(&t);
#endif
    }
    return -1;
}

// Current UTC time as time_t.
time_t utc_now()
{
    return std::time(nullptr);
}

std::string trim_copy(const std::string& value)
{
    const auto begin = value.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) return "";
    const auto end = value.find_last_not_of(" \t\r\n");
    return value.substr(begin, end - begin + 1);
}

std::string to_lower_copy(const std::string& value)
{
    std::string out = value;
    std::transform(out.begin(), out.end(), out.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return out;
}

std::string normalize_architecture(const std::string& value)
{
    const std::string normalized = to_lower_copy(trim_copy(value));
    if (normalized == "amd64" || normalized == "x64") return "x86_64";
    if (normalized == "aarch64") return "arm64";
    if (normalized == "armhf") return "armv7";
    return normalized;
}

std::string detect_current_operating_system()
{
#if defined(__ANDROID__)
    return "android";
#elif defined(_WIN32)
    return "windows";
#elif defined(__APPLE__)
#if defined(TARGET_OS_IPHONE) && TARGET_OS_IPHONE
    return "ios";
#else
    return "macos";
#endif
#elif defined(__linux__)
    return "linux";
#else
    return "";
#endif
}

std::string detect_current_architecture()
{
#if defined(__x86_64__) || defined(_M_X64)
    return "x86_64";
#elif defined(__aarch64__)
    return "arm64";
#elif defined(__i386__) || defined(_M_IX86)
    return "x86";
#elif defined(__arm__) || defined(_M_ARM)
    return "armv7";
#else
    return "";
#endif
}

std::string detect_current_os_version()
{
    const char* override_version = std::getenv("AI_OS_VERSION");
    if (override_version && override_version[0] != '\0') {
        return trim_copy(override_version);
    }

#if defined(__linux__) && !defined(__ANDROID__)
    std::ifstream input("/etc/os-release");
    std::string line;
    while (std::getline(input, line)) {
        if (line.rfind("VERSION_ID=", 0) != 0) continue;
        std::string value = line.substr(std::strlen("VERSION_ID="));
        value = trim_copy(value);
        if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.size() - 2);
        }
        return trim_copy(value);
    }
#endif
    return "";
}

std::vector<int> extract_version_segments(const std::string& value)
{
    std::vector<int> segments;
    const std::string trimmed = trim_copy(value);
    std::string current;
    for (char ch : trimmed) {
        if (std::isdigit(static_cast<unsigned char>(ch))) {
            current.push_back(ch);
            continue;
        }
        if (!current.empty()) {
            segments.push_back(std::atoi(current.c_str()));
            current.clear();
        }
    }
    if (!current.empty()) {
        segments.push_back(std::atoi(current.c_str()));
    }
    return segments;
}

bool minimum_version_satisfied(const std::string& current_version,
                               const std::string& minimum_required)
{
    const std::string required = trim_copy(minimum_required);
    if (required.empty()) return true;

    const std::string current = trim_copy(current_version);
    if (current.empty()) return false;

    const std::vector<int> current_segments = extract_version_segments(current);
    const std::vector<int> required_segments = extract_version_segments(required);
    if (current_segments.empty() || required_segments.empty()) {
        return current == required;
    }

    const size_t len = std::max(current_segments.size(), required_segments.size());
    for (size_t i = 0; i < len; ++i) {
        const int lhs = i < current_segments.size() ? current_segments[i] : 0;
        const int rhs = i < required_segments.size() ? required_segments[i] : 0;
        if (lhs < rhs) return false;
        if (lhs > rhs) return true;
    }
    return true;
}

bool environment_matches(const LicenseData& license_data)
{
    const std::string required_os = to_lower_copy(trim_copy(license_data.operating_system));
    if (!required_os.empty()) {
        const std::string current_os = detect_current_operating_system();
        if (current_os.empty() || current_os != required_os) {
            return false;
        }
    }

    const std::string required_arch = normalize_architecture(license_data.system_architecture);
    if (!required_arch.empty()) {
        const std::string current_arch = normalize_architecture(detect_current_architecture());
        if (current_arch.empty() || current_arch != required_arch) {
            return false;
        }
    }

    if (!minimum_version_satisfied(detect_current_os_version(), license_data.minimum_os_version)) {
        return false;
    }

    return true;
}

}  // namespace

// ---------------------------------------------------------------------------
// Public API implementations
// ---------------------------------------------------------------------------

const char* verify_result_str(VerifyResult r)
{
    switch (r) {
        case VerifyResult::OK:                   return "OK";
        case VerifyResult::SIGNATURE_INVALID:    return "SIGNATURE_INVALID";
        case VerifyResult::EXPIRED:              return "EXPIRED";
        case VerifyResult::NOT_YET_VALID:        return "NOT_YET_VALID";
        case VerifyResult::FINGERPRINT_MISMATCH: return "FINGERPRINT_MISMATCH";
        case VerifyResult::ENVIRONMENT_MISMATCH: return "ENVIRONMENT_MISMATCH";
        case VerifyResult::CAPABILITY_NOT_LICENSED: return "CAPABILITY_NOT_LICENSED";
        case VerifyResult::PARSE_ERROR:          return "PARSE_ERROR";
    }
    return "UNKNOWN";
}

bool generate_license(LicenseData&       license_data,
                      const std::string& privkey_path,
                      const std::string& output_path)
{
    const std::string privkey_pem = read_text_file(privkey_path);
    if (privkey_pem.empty()) return false;

    // Serialize all non-signature fields as the signing payload
    const std::string payload = serialize_payload(license_data);

    const std::string sig = rsa_sign(privkey_pem, payload);
    if (sig.empty()) return false;

    license_data.signature = sig;

    const std::string full_json = serialize_full(license_data);
    return write_text_file(output_path, full_json);
}

VerifyResult verify_license(const std::string& license_path,
                             const std::string& pubkey_path,
                             const std::string& machine_fp,
                             const std::string& required_capability)
{
    const std::string json = read_text_file(license_path);
    if (json.empty()) return VerifyResult::PARSE_ERROR;

    LicenseData ld;
    if (!parse_license_json(json, ld)) return VerifyResult::PARSE_ERROR;

    const std::string pubkey_pem = read_text_file(pubkey_path);
    if (pubkey_pem.empty()) return VerifyResult::PARSE_ERROR;

    // Re-build the payload (without signature) and verify
    const std::string payload = serialize_payload(ld);
    if (!rsa_verify(pubkey_pem, payload, ld.signature)) {
        return VerifyResult::SIGNATURE_INVALID;
    }

    const time_t now = utc_now();

    // Check valid_from
    if (!ld.valid_from.empty()) {
        const time_t from = parse_iso8601(ld.valid_from);
        if (from != -1 && now < from) {
            return VerifyResult::NOT_YET_VALID;
        }
    }

    // Check valid_until
    if (!ld.valid_until.empty()) {
        const time_t until = parse_iso8601(ld.valid_until);
        if (until != -1 && now > until) {
            return VerifyResult::EXPIRED;
        }
    }

    // Check machine fingerprint (if caller provides one)
    if (!machine_fp.empty() && !ld.machine_fingerprint.empty()) {
        if (machine_fp != ld.machine_fingerprint) {
            return VerifyResult::FINGERPRINT_MISMATCH;
        }
    }

    if (!environment_matches(ld)) {
        return VerifyResult::ENVIRONMENT_MISMATCH;
    }

    // Check required capability
    if (!required_capability.empty()) {
        bool found = false;
        for (const auto& cap : ld.capabilities) {
            if (cap == "*" || cap == required_capability) {
                found = true;
                break;
            }
        }
        if (!found) return VerifyResult::CAPABILITY_NOT_LICENSED;
    }

    return VerifyResult::OK;
}

bool load_license(const std::string& license_path, LicenseData& out)
{
    const std::string json = read_text_file(license_path);
    if (json.empty()) return false;
    return parse_license_json(json, out);
}
