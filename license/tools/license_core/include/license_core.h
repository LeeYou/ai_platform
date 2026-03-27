#ifndef AGILESTAR_LICENSE_CORE_H
#define AGILESTAR_LICENSE_CORE_H

/**
 * license_core.h
 * Public C++ API for AI platform license sign / verify operations.
 */

#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// License data payload
// ---------------------------------------------------------------------------
struct LicenseData {
    std::string license_id;           // "LS-YYYYMMDD-NNNN"
    std::string customer_id;
    std::string customer_name;
    std::string license_type;         // "trial" | "commercial" | "permanent"
    std::vector<std::string> capabilities; // ["face_detect", ...] or ["*"]
    std::string machine_fingerprint;  // "sha256:..." or ""
    std::string valid_from;           // ISO8601 UTC
    std::string valid_until;          // ISO8601 UTC or "" (empty = no expiry)
    std::string version_constraint;   // ">=1.0.0,<2.0.0"
    int         max_instances = 4;
    std::string issuer        = "agilestar.cn";
    std::string issued_at;            // ISO8601 UTC
    std::string signature;            // base64 RSA-SHA256 (excluded from signed payload)
};

// ---------------------------------------------------------------------------
// Verification result codes
// ---------------------------------------------------------------------------
enum class VerifyResult {
    OK = 0,
    SIGNATURE_INVALID,
    EXPIRED,
    NOT_YET_VALID,
    FINGERPRINT_MISMATCH,
    CAPABILITY_NOT_LICENSED,
    PARSE_ERROR
};

// Returns a human-readable description of a VerifyResult value.
const char* verify_result_str(VerifyResult r);

// ---------------------------------------------------------------------------
// Core API
// ---------------------------------------------------------------------------

/// Generates machine fingerprint using CPU/board serial + first NIC MAC,
/// hashed with SHA-256. Returns "sha256:<hex>".
std::string collect_fingerprint();

/// Generates an RSA-2048 key pair, writing PEM files to the given paths.
/// Returns true on success.
bool generate_keypair(const std::string& privkey_path,
                      const std::string& pubkey_path);

/// Signs license_data with the private key PEM file, sets
/// license_data.signature, then serialises the full payload to output_path.
/// Returns true on success.
bool generate_license(LicenseData&       license_data,
                      const std::string& privkey_path,
                      const std::string& output_path);

/// Reads a license file, verifies its RSA-SHA256 signature against pubkey_path,
/// and optionally checks expiry, machine fingerprint, and required capability.
/// Returns VerifyResult::OK on full success.
VerifyResult verify_license(const std::string& license_path,
                             const std::string& pubkey_path,
                             const std::string& machine_fp          = "",
                             const std::string& required_capability = "");

/// Loads license data from a file without verifying the signature.
/// Returns true on success.
bool load_license(const std::string& license_path, LicenseData& out);

#endif /* AGILESTAR_LICENSE_CORE_H */
