/**
 * license_io.cpp
 * JSON serializer/parser for LicenseData using nlohmann/json.
 *
 * Serialization rules:
 *   - serialize_payload: compact JSON with sorted keys (no signature field).
 *     Used as the signing payload in generate_license / verify_license.
 *   - serialize_full: compact JSON with sorted keys including the signature field.
 *     Written to the .bin license file.
 *   - parse_license_json: accepts any valid JSON format (compact or pretty-printed).
 */

#include "license_io.h"

#include <cstdio>
#include <string>

#include <nlohmann/json.hpp>

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------
namespace {

// Build a nlohmann::json object from LicenseData (all fields, no signature).
nlohmann::json ld_to_json_payload(const LicenseData& ld)
{
    // nlohmann::json uses std::map internally, so keys are always sorted.
    nlohmann::json j;
    j["capabilities"]        = ld.capabilities;
    j["application_name"]    = ld.application_name;
    j["customer_id"]         = ld.customer_id;
    j["customer_name"]       = ld.customer_name;
    j["issued_at"]           = ld.issued_at;
    j["issuer"]              = ld.issuer;
    j["license_id"]          = ld.license_id;
    j["license_type"]        = ld.license_type;
    j["machine_fingerprint"] = ld.machine_fingerprint;
    j["max_instances"]       = ld.max_instances;
    j["minimum_os_version"]  = ld.minimum_os_version;
    j["operating_system"]    = ld.operating_system;
    j["system_architecture"] = ld.system_architecture;
    j["valid_from"]          = ld.valid_from;
    j["valid_until"]         = ld.valid_until;
    j["version_constraint"]  = ld.version_constraint;
    return j;
}

}  // namespace

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

std::string serialize_payload(const LicenseData& ld)
{
    // Compact JSON, sorted keys, non-ASCII kept as-is —
    // matches Python's json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False).
    return ld_to_json_payload(ld).dump(-1, ' ', false);
}

std::string serialize_full(const LicenseData& ld)
{
    nlohmann::json j = ld_to_json_payload(ld);
    j["signature"] = ld.signature;
    return j.dump(-1, ' ', false);
}

bool parse_license_json(const std::string& json, LicenseData& ld)
{
    nlohmann::json j;
    try {
        j = nlohmann::json::parse(json);
    } catch (const nlohmann::json::exception&) {
        return false;
    }
    if (!j.is_object()) return false;

    const auto get_str = [&](const char* key) -> std::string {
        auto it = j.find(key);
        if (it == j.end() || it->is_null()) return "";
        if (it->is_string()) return it->get<std::string>();
        return "";
    };

    ld.license_id          = get_str("license_id");
    ld.customer_id         = get_str("customer_id");
    ld.customer_name       = get_str("customer_name");
    ld.license_type        = get_str("license_type");
    ld.operating_system    = get_str("operating_system");
    ld.minimum_os_version  = get_str("minimum_os_version");
    ld.system_architecture = get_str("system_architecture");
    ld.application_name    = get_str("application_name");
    ld.machine_fingerprint = get_str("machine_fingerprint");
    ld.valid_from          = get_str("valid_from");
    ld.valid_until         = get_str("valid_until");
    ld.version_constraint  = get_str("version_constraint");
    ld.issuer              = get_str("issuer");
    ld.issued_at           = get_str("issued_at");
    ld.signature           = get_str("signature");

    auto caps_it = j.find("capabilities");
    if (caps_it != j.end() && caps_it->is_array()) {
        ld.capabilities.clear();
        for (const auto& cap : *caps_it) {
            if (cap.is_string()) {
                ld.capabilities.push_back(cap.get<std::string>());
            }
        }
    }

    auto max_it = j.find("max_instances");
    if (max_it != j.end() && max_it->is_number_integer()) {
        ld.max_instances = max_it->get<int>();
    }

    return true;
}

bool write_text_file(const std::string& path, const std::string& content)
{
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) return false;
    const size_t written = fwrite(content.data(), 1, content.size(), f);
    fclose(f);
    return written == content.size();
}

std::string read_text_file(const std::string& path)
{
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return "";
    fseek(f, 0, SEEK_END);
    const long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (sz <= 0) { fclose(f); return ""; }
    std::string buf(static_cast<size_t>(sz), '\0');
    fread(buf.data(), 1, static_cast<size_t>(sz), f);
    fclose(f);
    return buf;
}
