#ifndef AGILESTAR_LICENSE_IO_H
#define AGILESTAR_LICENSE_IO_H

/**
 * license_io.h
 * JSON serialization / deserialization for LicenseData.
 * Base64 encode / decode helpers (backed by OpenSSL BIO).
 */

#include "include/license_core.h"

#include <string>

/// Serializes all LicenseData fields EXCEPT signature to a canonical JSON
/// string with keys in a fixed sorted order.  Used as the signed payload.
std::string serialize_payload(const LicenseData& ld);

/// Serializes all LicenseData fields INCLUDING signature to JSON.
std::string serialize_full(const LicenseData& ld);

/// Parses a JSON string into ld.  Returns false on parse errors.
bool parse_license_json(const std::string& json, LicenseData& ld);

/// Writes a string to a file. Returns false on error.
bool write_text_file(const std::string& path, const std::string& content);

/// Reads an entire file into a string. Returns empty string on error.
std::string read_text_file(const std::string& path);

#endif /* AGILESTAR_LICENSE_IO_H */
