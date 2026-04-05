/**
 * license_checker.cpp
 * License 校验（读取并解析 license.bin），结果缓存并异步刷新
 *
 * 安全设计：
 *   编译时通过 -DTRUSTED_PUBKEY_SHA256="<hex>" 将受信公钥的 SHA-256
 *   指纹硬编码进 SO。运行时加载 pubkey.pem 后先比对指纹，不匹配则
 *   拒绝验证——防止攻击者替换公钥+伪造授权绕过签名校验。
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "ai_runtime_impl.h"

#include <atomic>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#include <sys/stat.h>

#if defined(AI_HAVE_OPENSSL) && AI_HAVE_OPENSSL
#include <openssl/bio.h>
#include <openssl/buffer.h>
#include <openssl/evp.h>
#include <openssl/pem.h>
#include <openssl/rsa.h>
#include <iomanip>
#endif

#ifndef TRUSTED_PUBKEY_SHA256
#define TRUSTED_PUBKEY_SHA256 ""
#endif

namespace {

static int64_t _unix_time_ms_now() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();
}

static int64_t _file_mtime_seconds(const std::string& path) {
    if (path.empty()) return -1;
    struct stat st = {};
    if (::stat(path.c_str(), &st) != 0) return -1;
    return static_cast<int64_t>(st.st_mtime);
}

static bool _read_file(const std::string& path, std::string& out) {
    std::ifstream input(path, std::ios::binary);
    if (!input.is_open()) return false;
    out.assign((std::istreambuf_iterator<char>(input)),
               std::istreambuf_iterator<char>());
    return true;
}

static std::string _derive_pubkey_path(const std::string& license_path) {
    if (license_path.empty()) return "";
    auto slash = license_path.find_last_of("/\\");
    if (slash == std::string::npos) return "";
    return license_path.substr(0, slash + 1) + "pubkey.pem";
}

static std::string _json_escape(const std::string& value) {
    std::string escaped;
    escaped.reserve(value.size());
    for (char ch : value) {
        switch (ch) {
            case '\\': escaped += "\\\\"; break;
            case '"':  escaped += "\\\""; break;
            case '\n': escaped += "\\n"; break;
            case '\r': escaped += "\\r"; break;
            case '\t': escaped += "\\t"; break;
            default:   escaped += ch; break;
        }
    }
    return escaped;
}

static std::string _trim_copy(const std::string& value) {
    const auto begin = value.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) return "";
    const auto end = value.find_last_not_of(" \t\r\n");
    return value.substr(begin, end - begin + 1);
}

static std::string _json_string(const std::string& json, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return "";
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return "";
    auto end = json.find('"', pos + 1);
    if (end == std::string::npos) return "";
    return json.substr(pos + 1, end - pos - 1);
}

static int32_t _compute_days_remaining(const std::string& iso_time) {
    if (iso_time.empty() || iso_time == "null") return -1;

    struct tm tm_value = {};
    if (std::sscanf(iso_time.c_str(), "%4d-%2d-%2dT%2d:%2d:%2d",
                    &tm_value.tm_year,
                    &tm_value.tm_mon,
                    &tm_value.tm_mday,
                    &tm_value.tm_hour,
                    &tm_value.tm_min,
                    &tm_value.tm_sec) < 3) {
        return 0;
    }

    tm_value.tm_year -= 1900;
    tm_value.tm_mon  -= 1;

#ifdef _WIN32
    time_t ts = _mkgmtime(&tm_value) - (8 * 3600);
#else
    time_t ts = timegm(&tm_value) - (8 * 3600);
#endif
    const time_t now = time(nullptr);
    const double diff_days = std::difftime(ts, now) / 86400.0;
    return static_cast<int32_t>(std::floor(diff_days));
}

static std::pair<bool, int32_t> _check_valid_from(const std::string& valid_from) {
    if (valid_from.empty() || valid_from == "null") return {true, 0};
    const int32_t days_until = _compute_days_remaining(valid_from);
    if (days_until <= 0) return {true, 0};
    return {false, days_until};
}

struct ParsedJsonObject {
    std::unordered_map<std::string, std::string> values;
};

static bool _skip_ws(const std::string& json, size_t& pos) {
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\r' || json[pos] == '\n')) {
        ++pos;
    }
    return pos < json.size();
}

static bool _parse_json_string_token(const std::string& json, size_t& pos, std::string& out) {
    if (!_skip_ws(json, pos) || json[pos] != '"') return false;
    ++pos;
    out.clear();
    while (pos < json.size()) {
        const char ch = json[pos++];
        if (ch == '"') return true;
        if (ch == '\\') {
            if (pos >= json.size()) return false;
            const char esc = json[pos++];
            switch (esc) {
                case '"': out.push_back('"'); break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/'); break;
                case 'b': out.push_back('\b'); break;
                case 'f': out.push_back('\f'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                default: return false;
            }
            continue;
        }
        out.push_back(ch);
    }
    return false;
}

static bool _find_json_value_end(const std::string& json, size_t start, size_t& end) {
    size_t pos = start;
    if (!_skip_ws(json, pos)) return false;
    start = pos;

    if (json[pos] == '"') {
        ++pos;
        while (pos < json.size()) {
            if (json[pos] == '\\') {
                pos += 2;
                continue;
            }
            if (json[pos] == '"') {
                end = pos + 1;
                return true;
            }
            ++pos;
        }
        return false;
    }

    if (json[pos] == '{' || json[pos] == '[') {
        const char open = json[pos];
        const char close = (open == '{') ? '}' : ']';
        int depth = 0;
        bool in_string = false;
        for (; pos < json.size(); ++pos) {
            const char ch = json[pos];
            if (in_string) {
                if (ch == '\\') {
                    ++pos;
                    continue;
                }
                if (ch == '"') in_string = false;
                continue;
            }
            if (ch == '"') {
                in_string = true;
                continue;
            }
            if (ch == open) {
                ++depth;
                continue;
            }
            if (ch == close) {
                --depth;
                if (depth == 0) {
                    end = pos + 1;
                    return true;
                }
            }
        }
        return false;
    }

    while (pos < json.size() && json[pos] != ',' && json[pos] != '}') {
        ++pos;
    }
    end = pos;
    return true;
}

static bool _parse_top_level_json_object(const std::string& json, ParsedJsonObject& parsed) {
    parsed.values.clear();
    size_t pos = 0;
    if (!_skip_ws(json, pos) || json[pos] != '{') return false;
    ++pos;

    while (true) {
        if (!_skip_ws(json, pos)) return false;
        if (json[pos] == '}') return true;

        std::string key;
        if (!_parse_json_string_token(json, pos, key)) return false;
        if (!_skip_ws(json, pos) || json[pos] != ':') return false;
        ++pos;

        size_t value_start = pos;
        size_t value_end = pos;
        if (!_find_json_value_end(json, value_start, value_end)) return false;
        parsed.values[key] = _trim_copy(json.substr(value_start, value_end - value_start));
        pos = value_end;

        if (!_skip_ws(json, pos)) return false;
        if (json[pos] == '}') return true;
        if (json[pos] != ',') return false;
        ++pos;
    }
}

#if defined(AI_HAVE_OPENSSL) && AI_HAVE_OPENSSL
static std::string _sha256_hex(const std::string& data) {
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) return "";
    if (EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }
    if (EVP_DigestUpdate(ctx, data.data(), data.size()) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int digest_len = 0;
    if (EVP_DigestFinal_ex(ctx, digest, &digest_len) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }
    EVP_MD_CTX_free(ctx);

    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (unsigned int i = 0; i < digest_len; ++i) {
        oss << std::setw(2) << static_cast<unsigned int>(digest[i]);
    }
    return oss.str();
}

static bool _decode_base64(const std::string& encoded, std::vector<unsigned char>& out) {
    out.clear();
    BIO* b64 = BIO_new(BIO_f_base64());
    BIO* mem = BIO_new_mem_buf(encoded.data(), static_cast<int>(encoded.size()));
    if (!b64 || !mem) {
        if (b64) BIO_free(b64);
        if (mem) BIO_free(mem);
        return false;
    }
    BIO_set_flags(b64, BIO_FLAGS_BASE64_NO_NL);
    mem = BIO_push(b64, mem);

    out.resize(encoded.size());
    const int read_len = BIO_read(mem, out.data(), static_cast<int>(out.size()));
    BIO_free_all(mem);
    if (read_len <= 0) {
        out.clear();
        return false;
    }
    out.resize(static_cast<size_t>(read_len));
    return true;
}

static bool _verify_pubkey_fingerprint(const std::string& pubkey_path) {
    const std::string trusted(TRUSTED_PUBKEY_SHA256);
    if (trusted.empty()) return true;

    std::string pem;
    if (!_read_file(pubkey_path, pem)) {
        std::fprintf(stderr, "[LicenseChecker] Cannot open pubkey for fingerprint check: %s\n",
                     pubkey_path.c_str());
        return false;
    }

    const std::string actual = _sha256_hex(pem);
    if (actual != trusted) {
        std::fprintf(stderr,
                     "[LicenseChecker] ❌ Public key fingerprint MISMATCH!\n"
                     "  expected: %s\n"
                     "  actual:   %s\n"
                     "  Possible tampering — license verification DENIED.\n",
                     trusted.c_str(), actual.c_str());
        return false;
    }

    std::fprintf(stdout, "[LicenseChecker] ✅ Public key fingerprint verified.\n");
    return true;
}

static bool _verify_signature(const std::string& canonical_json,
                              const std::string& signature_b64,
                              const std::string& pubkey_pem) {
    std::vector<unsigned char> signature;
    if (!_decode_base64(signature_b64, signature)) return false;

    BIO* key_bio = BIO_new_mem_buf(pubkey_pem.data(), static_cast<int>(pubkey_pem.size()));
    if (!key_bio) return false;
    EVP_PKEY* public_key = PEM_read_bio_PUBKEY(key_bio, nullptr, nullptr, nullptr);
    BIO_free(key_bio);
    if (!public_key) return false;

    EVP_MD_CTX* md_ctx = EVP_MD_CTX_new();
    if (!md_ctx) {
        EVP_PKEY_free(public_key);
        return false;
    }

    EVP_PKEY_CTX* pkey_ctx = nullptr;
    bool ok = false;
    if (EVP_DigestVerifyInit(md_ctx, &pkey_ctx, EVP_sha256(), nullptr, public_key) == 1 &&
        EVP_PKEY_CTX_set_rsa_padding(pkey_ctx, RSA_PKCS1_PSS_PADDING) == 1 &&
        EVP_PKEY_CTX_set_rsa_mgf1_md(pkey_ctx, EVP_sha256()) == 1 &&
        EVP_PKEY_CTX_set_rsa_pss_saltlen(pkey_ctx, RSA_PSS_SALTLEN_AUTO) == 1 &&
        EVP_DigestVerifyUpdate(md_ctx, canonical_json.data(), canonical_json.size()) == 1 &&
        EVP_DigestVerifyFinal(md_ctx, signature.data(), signature.size()) == 1) {
        ok = true;
    }

    EVP_MD_CTX_free(md_ctx);
    EVP_PKEY_free(public_key);
    return ok;
}
#else
static bool _verify_pubkey_fingerprint(const std::string&) {
    const std::string trusted(TRUSTED_PUBKEY_SHA256);
    if (!trusted.empty()) {
        std::fprintf(stderr, "[LicenseChecker] OpenSSL not available but TRUSTED_PUBKEY_SHA256 is set — DENIED.\n");
        return false;
    }
    return true;
}
#endif

}  // namespace

namespace agilestar {

struct LicenseStatus {
    bool        valid = false;
    bool        expired = false;
    bool        not_yet_valid = false;
    bool        missing = false;
    bool        signature_invalid = false;
    std::string status = "invalid";
    std::string license_id;
    std::string valid_from;
    std::string valid_until;
    int32_t     days_remaining = 0;
    std::vector<std::string> capabilities;
    std::string raw_json;
    int64_t     source_mtime = -1;
    int64_t     refreshed_at_ms = 0;
    int64_t     last_success_at_ms = 0;
    std::string last_error;
    std::chrono::steady_clock::time_point refreshed_monotonic{};
};

class LicenseCache {
public:
    static LicenseCache& instance() {
        static LicenseCache cache;
        return cache;
    }

    ~LicenseCache() {
        stop_.store(true);
    }

    void set_license_path(const std::string& path) {
        {
            std::lock_guard<std::mutex> lk(config_mutex_);
            license_path_ = path;
            parsed_license_path_.clear();
            parsed_license_mtime_ = -1;
        }
        refresh_now();
    }

    void set_pubkey_path(const std::string& path) {
        {
            std::lock_guard<std::mutex> lk(config_mutex_);
            pubkey_path_ = path;
            verified_pubkey_path_.clear();
            verified_pubkey_mtime_ = -1;
        }
        refresh_now();
    }

    LicenseStatus get() {
        auto snapshot = std::atomic_load(&snapshot_);
        if (!snapshot) {
            refresh_now();
            snapshot = std::atomic_load(&snapshot_);
        }
        if (!snapshot) {
            LicenseStatus empty;
            empty.status = "invalid";
            empty.last_error = "license snapshot unavailable";
            empty.refreshed_at_ms = _unix_time_ms_now();
            empty.refreshed_monotonic = std::chrono::steady_clock::now();
            return empty;
        }

        if (std::chrono::steady_clock::now() - snapshot->refreshed_monotonic > cache_ttl_) {
            refresh_async();
        }
        return *snapshot;
    }

    bool is_capability_licensed(const std::string& cap_name) {
        const LicenseStatus status = get();
        if (!status.valid || status.expired || status.not_yet_valid || status.signature_invalid || status.missing) {
            return false;
        }
        for (const auto& licensed : status.capabilities) {
            if (licensed == "*" || licensed == cap_name) return true;
        }
        return false;
    }

    std::string to_json() {
        const LicenseStatus status = get();
        std::ostringstream os;
        os << "{"
           << "\"status\":\"" << _json_escape(status.status) << "\""
           << ",\"license_id\":";
        if (status.license_id.empty()) {
            os << "null";
        } else {
            os << "\"" << _json_escape(status.license_id) << "\"";
        }
        os << ",\"valid_from\":";
        if (status.valid_from.empty()) {
            os << "null";
        } else {
            os << "\"" << _json_escape(status.valid_from) << "\"";
        }
        os << ",\"valid_until\":";
        if (status.valid_until.empty()) {
            os << "null";
        } else {
            os << "\"" << _json_escape(status.valid_until) << "\"";
        }
        os << ",\"days_remaining\":" << status.days_remaining
           << ",\"source_mtime\":" << status.source_mtime
           << ",\"refreshed_at_ms\":" << status.refreshed_at_ms
           << ",\"last_success_at_ms\":" << status.last_success_at_ms
           << ",\"last_error\":\"" << _json_escape(status.last_error) << "\""
           << ",\"capabilities\":[";
        for (size_t i = 0; i < status.capabilities.size(); ++i) {
            if (i > 0) os << ",";
            os << "\"" << _json_escape(status.capabilities[i]) << "\"";
        }
        os << "]}";
        return os.str();
    }

private:
    LicenseCache() = default;

    void refresh_async() {
        bool expected = false;
        if (!refresh_in_progress_.compare_exchange_strong(expected, true)) return;

        std::thread([this]() {
            this->refresh_publish();
            refresh_in_progress_.store(false);
        }).detach();
    }

    void refresh_now() {
        bool expected = false;
        if (refresh_in_progress_.compare_exchange_strong(expected, true)) {
            refresh_publish();
            refresh_in_progress_.store(false);
            return;
        }

        while (refresh_in_progress_.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }

    void refresh_publish() {
        if (stop_.load()) return;
        auto next = build_snapshot();
        std::atomic_store(&snapshot_, std::shared_ptr<const LicenseStatus>(std::move(next)));
    }

    static void update_temporal_status(LicenseStatus& status) {
        status.valid = false;
        status.expired = false;
        status.not_yet_valid = false;
        status.days_remaining = 0;

        if (status.signature_invalid) {
            status.status = "signature_invalid";
            return;
        }
        if (status.missing) {
            status.status = "missing";
            return;
        }

        const auto [has_started, days_until_start] = _check_valid_from(status.valid_from);
        if (!has_started) {
            status.status = "not_yet_valid";
            status.not_yet_valid = true;
            status.days_remaining = -days_until_start;
            return;
        }

        const int32_t days = _compute_days_remaining(status.valid_until);
        if (days < 0) {
            status.status = "valid";
            status.valid = true;
            status.days_remaining = -1;
            return;
        }
        if (days <= 0) {
            status.status = "expired";
            status.expired = true;
            status.days_remaining = 0;
            return;
        }

        status.status = "valid";
        status.valid = true;
        status.days_remaining = days;
    }

    std::shared_ptr<LicenseStatus> build_snapshot() {
        auto current = std::atomic_load(&snapshot_);
        auto next = current ? std::make_shared<LicenseStatus>(*current)
                            : std::make_shared<LicenseStatus>();

        next->refreshed_at_ms = _unix_time_ms_now();
        next->refreshed_monotonic = std::chrono::steady_clock::now();

        std::string license_path;
        std::string configured_pubkey_path;
        std::string parsed_license_path;
        std::string verified_pubkey_path;
        int64_t parsed_license_mtime = -1;
        int64_t verified_pubkey_mtime = -1;
        {
            std::lock_guard<std::mutex> lk(config_mutex_);
            license_path = license_path_;
            configured_pubkey_path = pubkey_path_;
            parsed_license_path = parsed_license_path_;
            verified_pubkey_path = verified_pubkey_path_;
            parsed_license_mtime = parsed_license_mtime_;
            verified_pubkey_mtime = verified_pubkey_mtime_;
        }

        if (license_path.empty()) {
            *next = LicenseStatus{};
            next->status = "invalid";
            next->last_error = "no license path configured";
            next->refreshed_at_ms = _unix_time_ms_now();
            next->refreshed_monotonic = std::chrono::steady_clock::now();
            return next;
        }

        const std::string effective_pubkey_path =
            !configured_pubkey_path.empty() ? configured_pubkey_path : _derive_pubkey_path(license_path);
        const int64_t license_mtime = _file_mtime_seconds(license_path);
        const int64_t pubkey_mtime = effective_pubkey_path.empty() ? -1 : _file_mtime_seconds(effective_pubkey_path);

        if (license_mtime < 0) {
            *next = LicenseStatus{};
            next->status = "missing";
            next->missing = true;
            next->last_error = "license file not found";
            next->source_mtime = -1;
            next->refreshed_at_ms = _unix_time_ms_now();
            next->refreshed_monotonic = std::chrono::steady_clock::now();
            return next;
        }

        const bool pubkey_changed =
            effective_pubkey_path != verified_pubkey_path || pubkey_mtime != verified_pubkey_mtime;
        if (pubkey_changed) {
            if (!_verify_pubkey_fingerprint(effective_pubkey_path)) {
                *next = LicenseStatus{};
                next->status = "invalid";
                next->last_error = "trusted public key fingerprint verification failed";
                next->source_mtime = license_mtime;
                next->refreshed_at_ms = _unix_time_ms_now();
                next->refreshed_monotonic = std::chrono::steady_clock::now();
                return next;
            }
            std::lock_guard<std::mutex> lk(config_mutex_);
            verified_pubkey_path_ = effective_pubkey_path;
            verified_pubkey_mtime_ = pubkey_mtime;
        }

        const bool need_reparse =
            !current ||
            license_path != parsed_license_path ||
            license_mtime != parsed_license_mtime ||
            effective_pubkey_path != verified_pubkey_path;

        if (need_reparse) {
            std::string content;
            if (!_read_file(license_path, content)) {
                if (current && license_path == parsed_license_path && license_mtime == parsed_license_mtime) {
                    next->last_error = "license file temporarily unreadable";
                    return next;
                }
                *next = LicenseStatus{};
                next->status = "invalid";
                next->last_error = "unable to read license file";
                next->source_mtime = license_mtime;
                next->refreshed_at_ms = _unix_time_ms_now();
                next->refreshed_monotonic = std::chrono::steady_clock::now();
                return next;
            }

            const auto start = content.find('{');
            if (start == std::string::npos) {
                *next = LicenseStatus{};
                next->status = "invalid";
                next->last_error = "invalid license format";
                next->source_mtime = license_mtime;
                next->refreshed_at_ms = _unix_time_ms_now();
                next->refreshed_monotonic = std::chrono::steady_clock::now();
                return next;
            }

            const std::string json = content.substr(start);
            ParsedJsonObject parsed;
            if (!_parse_top_level_json_object(json, parsed)) {
                *next = LicenseStatus{};
                next->status = "invalid";
                next->last_error = "failed to parse license json";
                next->source_mtime = license_mtime;
                next->refreshed_at_ms = _unix_time_ms_now();
                next->refreshed_monotonic = std::chrono::steady_clock::now();
                return next;
            }

            next->capabilities.clear();
            next->license_id = _json_string(json, "license_id");
            next->valid_from = _json_string(json, "valid_from");
            next->valid_until = _json_string(json, "valid_until");
            next->raw_json = json;
            next->source_mtime = license_mtime;
            next->signature_invalid = false;
            next->missing = false;
            next->last_error.clear();

            const auto capabilities_it = parsed.values.find("capabilities");
            if (capabilities_it != parsed.values.end()) {
                const std::string& arr = capabilities_it->second;
                size_t p = 0;
                while (p < arr.size()) {
                    auto q1 = arr.find('"', p);
                    if (q1 == std::string::npos) break;
                    auto q2 = arr.find('"', q1 + 1);
                    if (q2 == std::string::npos) break;
                    next->capabilities.push_back(arr.substr(q1 + 1, q2 - q1 - 1));
                    p = q2 + 1;
                }
            }

#if defined(AI_HAVE_OPENSSL) && AI_HAVE_OPENSSL
            std::string pubkey_pem;
            if (!_read_file(effective_pubkey_path, pubkey_pem)) {
                *next = LicenseStatus{};
                next->status = "invalid";
                next->last_error = "unable to read public key";
                next->source_mtime = license_mtime;
                next->refreshed_at_ms = _unix_time_ms_now();
                next->refreshed_monotonic = std::chrono::steady_clock::now();
                return next;
            }

            auto signature_it = parsed.values.find("signature");
            if (signature_it == parsed.values.end()) {
                next->signature_invalid = true;
                next->status = "signature_invalid";
                next->last_error = "signature missing";
                next->source_mtime = license_mtime;
                next->refreshed_at_ms = _unix_time_ms_now();
                next->refreshed_monotonic = std::chrono::steady_clock::now();
                return next;
            }

            std::vector<std::string> keys;
            keys.reserve(parsed.values.size());
            for (const auto& item : parsed.values) {
                if (item.first != "signature") keys.push_back(item.first);
            }
            std::sort(keys.begin(), keys.end());

            std::ostringstream canonical;
            canonical << "{";
            for (size_t i = 0; i < keys.size(); ++i) {
                if (i > 0) canonical << ",";
                canonical << "\"" << _json_escape(keys[i]) << "\":" << parsed.values[keys[i]];
            }
            canonical << "}";

            std::string signature_b64 = signature_it->second;
            if (signature_b64.size() >= 2 && signature_b64.front() == '"' && signature_b64.back() == '"') {
                signature_b64 = signature_b64.substr(1, signature_b64.size() - 2);
            }

            if (!_verify_signature(canonical.str(), signature_b64, pubkey_pem)) {
                next->signature_invalid = true;
                next->status = "signature_invalid";
                next->last_error = "signature verification failed";
                next->source_mtime = license_mtime;
                next->refreshed_at_ms = _unix_time_ms_now();
                next->refreshed_monotonic = std::chrono::steady_clock::now();
                return next;
            }
#else
            if (!TRUSTED_PUBKEY_SHA256[0]) {
                next->last_error = "signature verification skipped (OpenSSL unavailable)";
            }
#endif

            update_temporal_status(*next);
            next->last_error.clear();
            next->last_success_at_ms = next->refreshed_at_ms;

            {
                std::lock_guard<std::mutex> lk(config_mutex_);
                parsed_license_path_ = license_path;
                parsed_license_mtime_ = license_mtime;
            }
        } else {
            update_temporal_status(*next);
            next->source_mtime = license_mtime;
            next->last_error.clear();
        }

        std::fprintf(stdout,
                     "[LicenseChecker] License %s: status=%s caps=%zu days_remaining=%d\n",
                     next->license_id.c_str(),
                     next->status.c_str(),
                     next->capabilities.size(),
                     next->days_remaining);
        return next;
    }

    std::mutex config_mutex_;
    std::string license_path_;
    std::string pubkey_path_;
    std::string parsed_license_path_;
    std::string verified_pubkey_path_;
    int64_t parsed_license_mtime_ = -1;
    int64_t verified_pubkey_mtime_ = -1;
    std::shared_ptr<const LicenseStatus> snapshot_;
    std::chrono::seconds cache_ttl_{30};
    std::atomic<bool> refresh_in_progress_{false};
    std::atomic<bool> stop_{false};
};

}  // namespace agilestar

void agilestar_license_set_path(const char* path) {
    agilestar::LicenseCache::instance().set_license_path(path ? path : "");
}

void agilestar_license_set_pubkey_path(const char* path) {
    agilestar::LicenseCache::instance().set_pubkey_path(path ? path : "");
}

bool agilestar_license_is_valid(const char* cap_name) {
    if (cap_name) {
        return agilestar::LicenseCache::instance().is_capability_licensed(cap_name);
    }
    return agilestar::LicenseCache::instance().get().valid;
}

int32_t agilestar_license_get_json(char* buf, int32_t buf_len) {
    const std::string json = agilestar::LicenseCache::instance().to_json();
    const int32_t needed = static_cast<int32_t>(json.size());
    if (!buf || buf_len <= needed) return needed;
    std::memcpy(buf, json.c_str(), static_cast<size_t>(needed) + 1);
    return needed;
}
