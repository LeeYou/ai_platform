/**
 * license_core.cpp
 * High-level API: generate_license() and verify_license().
 */

#include "include/license_core.h"
#include "license_io.h"
#include "rsa_utils.h"

#include <cstring>
#include <ctime>
#include <string>

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
