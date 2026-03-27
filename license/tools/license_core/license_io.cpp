/**
 * license_io.cpp
 * Minimal hand-written JSON serializer/parser for LicenseData.
 * No external JSON library is required.
 *
 * Serialization rules:
 *   - Keys are always in the fixed canonical order defined by serialize_payload /
 *     serialize_full so that the signed payload is reproducible.
 *   - Strings are escaped (", \, and control characters).
 *   - Arrays are serialized as JSON arrays of quoted strings.
 *   - Integers are serialized as JSON numbers.
 */

#include "license_io.h"

#include <algorithm>
#include <cstdio>
#include <sstream>
#include <string>

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------
namespace {

// JSON-escape a single string value (without surrounding quotes).
std::string json_escape(const std::string& s)
{
    std::string out;
    out.reserve(s.size() + 4);
    for (unsigned char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b";  break;
            case '\f': out += "\\f";  break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    snprintf(buf, sizeof(buf), "\\u%04x",
                             static_cast<unsigned int>(c));
                    out += buf;
                } else {
                    out += static_cast<char>(c);
                }
                break;
        }
    }
    return out;
}

// Emit a JSON key-value pair with a string value.
void emit_string(std::ostringstream& o, const std::string& key,
                 const std::string& value, bool comma = true)
{
    if (comma) o << ",\n";
    o << "  \"" << json_escape(key) << "\": \""
      << json_escape(value) << "\"";
}

// Emit a JSON key-value pair with an integer value.
void emit_int(std::ostringstream& o, const std::string& key, int value,
              bool comma = true)
{
    if (comma) o << ",\n";
    o << "  \"" << json_escape(key) << "\": " << value;
}

// Emit a JSON key-value pair with a string-array value.
void emit_array(std::ostringstream& o, const std::string& key,
                const std::vector<std::string>& arr, bool comma = true)
{
    if (comma) o << ",\n";
    o << "  \"" << json_escape(key) << "\": [";
    for (size_t i = 0; i < arr.size(); ++i) {
        if (i) o << ", ";
        o << "\"" << json_escape(arr[i]) << "\"";
    }
    o << "]";
}

// ---------------------------------------------------------------------------
// Parser helpers
// ---------------------------------------------------------------------------

// Skip whitespace at pos.
void skip_ws(const std::string& s, size_t& pos)
{
    while (pos < s.size() &&
           (s[pos] == ' ' || s[pos] == '\t' || s[pos] == '\n' ||
            s[pos] == '\r')) {
        ++pos;
    }
}

// Parse a JSON string starting at the opening '"'.  pos is left after the
// closing '"'.  Returns the decoded string or sets ok=false on error.
std::string parse_string(const std::string& s, size_t& pos, bool& ok)
{
    if (pos >= s.size() || s[pos] != '"') { ok = false; return ""; }
    ++pos;  // skip opening "
    std::string out;
    while (pos < s.size() && s[pos] != '"') {
        if (s[pos] == '\\') {
            ++pos;
            if (pos >= s.size()) { ok = false; return ""; }
            switch (s[pos]) {
                case '"':  out += '"';  break;
                case '\\': out += '\\'; break;
                case '/':  out += '/';  break;
                case 'b':  out += '\b'; break;
                case 'f':  out += '\f'; break;
                case 'n':  out += '\n'; break;
                case 'r':  out += '\r'; break;
                case 't':  out += '\t'; break;
                case 'u': {
                    // Parse \uXXXX
                    if (pos + 4 >= s.size()) { ok = false; return ""; }
                    std::string hex = s.substr(pos + 1, 4);
                    unsigned int cp = 0;
                    sscanf(hex.c_str(), "%x", &cp);
                    // Simple Latin-1 downcast for codepoints < 256
                    out += static_cast<char>(cp & 0xFF);
                    pos += 4;
                    break;
                }
                default: out += s[pos]; break;
            }
        } else {
            out += s[pos];
        }
        ++pos;
    }
    if (pos >= s.size()) { ok = false; return ""; }
    ++pos;  // skip closing "
    return out;
}

// Parse a JSON integer at pos.
int parse_int(const std::string& s, size_t& pos, bool& ok)
{
    size_t start = pos;
    if (pos < s.size() && s[pos] == '-') ++pos;
    while (pos < s.size() && s[pos] >= '0' && s[pos] <= '9') ++pos;
    if (pos == start) { ok = false; return 0; }
    return std::stoi(s.substr(start, pos - start));
}

// Parse a JSON array of strings at pos (starting at '[').
std::vector<std::string> parse_string_array(const std::string& s, size_t& pos,
                                            bool& ok)
{
    std::vector<std::string> arr;
    if (pos >= s.size() || s[pos] != '[') { ok = false; return arr; }
    ++pos;
    skip_ws(s, pos);
    if (pos < s.size() && s[pos] == ']') { ++pos; return arr; }
    while (pos < s.size()) {
        skip_ws(s, pos);
        if (pos >= s.size()) { ok = false; return arr; }
        arr.push_back(parse_string(s, pos, ok));
        if (!ok) return arr;
        skip_ws(s, pos);
        if (pos >= s.size()) { ok = false; return arr; }
        if (s[pos] == ',') { ++pos; continue; }
        if (s[pos] == ']') { ++pos; break; }
        ok = false; return arr;
    }
    return arr;
}

}  // namespace

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

std::string serialize_payload(const LicenseData& ld)
{
    // Canonical key order — signature is intentionally excluded.
    std::ostringstream out;
    out << "{\n";
    emit_array  (out, "capabilities",        ld.capabilities,        false);
    emit_string (out, "customer_id",         ld.customer_id);
    emit_string (out, "customer_name",       ld.customer_name);
    emit_string (out, "issued_at",           ld.issued_at);
    emit_string (out, "issuer",              ld.issuer);
    emit_string (out, "license_id",          ld.license_id);
    emit_string (out, "license_type",        ld.license_type);
    emit_string (out, "machine_fingerprint", ld.machine_fingerprint);
    emit_int    (out, "max_instances",       ld.max_instances);
    emit_string (out, "valid_from",          ld.valid_from);
    emit_string (out, "valid_until",         ld.valid_until);
    emit_string (out, "version_constraint",  ld.version_constraint);
    out << "\n}";
    return out.str();
}

std::string serialize_full(const LicenseData& ld)
{
    std::ostringstream out;
    out << "{\n";
    emit_array  (out, "capabilities",       ld.capabilities,        false);
    emit_string (out, "customer_id",        ld.customer_id);
    emit_string (out, "customer_name",      ld.customer_name);
    emit_string (out, "issued_at",          ld.issued_at);
    emit_string (out, "issuer",             ld.issuer);
    emit_string (out, "license_id",         ld.license_id);
    emit_string (out, "license_type",       ld.license_type);
    emit_string (out, "machine_fingerprint",ld.machine_fingerprint);
    emit_int    (out, "max_instances",      ld.max_instances);
    emit_string (out, "signature",          ld.signature);
    emit_string (out, "valid_from",         ld.valid_from);
    emit_string (out, "valid_until",        ld.valid_until);
    emit_string (out, "version_constraint", ld.version_constraint);
    out << "\n}";
    return out.str();
}

bool parse_license_json(const std::string& json, LicenseData& ld)
{
    bool ok = true;
    size_t pos = 0;
    skip_ws(json, pos);
    if (pos >= json.size() || json[pos] != '{') return false;
    ++pos;

    while (pos < json.size()) {
        skip_ws(json, pos);
        if (pos >= json.size()) { ok = false; break; }
        if (json[pos] == '}') { ++pos; break; }
        if (json[pos] == ',') { ++pos; continue; }

        // Parse key
        if (json[pos] != '"') { ok = false; break; }
        const std::string key = parse_string(json, pos, ok);
        if (!ok) break;

        skip_ws(json, pos);
        if (pos >= json.size() || json[pos] != ':') { ok = false; break; }
        ++pos;
        skip_ws(json, pos);

        // Parse value based on key
        if (key == "capabilities") {
            ld.capabilities = parse_string_array(json, pos, ok);
        } else if (key == "max_instances") {
            ld.max_instances = parse_int(json, pos, ok);
        } else {
            // All other values are strings
            if (pos >= json.size() || json[pos] != '"') { ok = false; break; }
            const std::string val = parse_string(json, pos, ok);
            if (!ok) break;

            if      (key == "license_id")          ld.license_id          = val;
            else if (key == "customer_id")         ld.customer_id         = val;
            else if (key == "customer_name")       ld.customer_name       = val;
            else if (key == "license_type")        ld.license_type        = val;
            else if (key == "machine_fingerprint") ld.machine_fingerprint = val;
            else if (key == "valid_from")          ld.valid_from          = val;
            else if (key == "valid_until")         ld.valid_until         = val;
            else if (key == "version_constraint")  ld.version_constraint  = val;
            else if (key == "issuer")              ld.issuer              = val;
            else if (key == "issued_at")           ld.issued_at           = val;
            else if (key == "signature")           ld.signature           = val;
            // Unknown keys are silently ignored for forward compatibility.
        }
        if (!ok) break;
    }
    return ok;
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
