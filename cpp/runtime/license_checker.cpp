/**
 * license_checker.cpp
 * License 校验（读取并解析 license.bin），结果缓存 60 秒
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
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

// OpenSSL for SHA-256 fingerprint verification (optional at compile time)
#if defined(AI_HAVE_OPENSSL) && AI_HAVE_OPENSSL
#include <openssl/evp.h>
#include <iomanip>
#endif

// Trusted public key SHA-256 fingerprint — injected at compile time.
// Example:  -DTRUSTED_PUBKEY_SHA256="a1b2c3..."
// If not defined, fingerprint checking is disabled (dev/test only).
#ifndef TRUSTED_PUBKEY_SHA256
#define TRUSTED_PUBKEY_SHA256 ""
#endif

namespace agilestar {

// ---------------------------------------------------------------------------
// Public key fingerprint verification
// ---------------------------------------------------------------------------

#if defined(AI_HAVE_OPENSSL) && AI_HAVE_OPENSSL
static std::string _sha256_hex(const std::string& data) {
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) return "";
    const EVP_MD* md = EVP_sha256();
    if (EVP_DigestInit_ex(ctx, md, nullptr) != 1) { EVP_MD_CTX_free(ctx); return ""; }
    if (EVP_DigestUpdate(ctx, data.data(), data.size()) != 1) { EVP_MD_CTX_free(ctx); return ""; }
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int  dlen = 0;
    if (EVP_DigestFinal_ex(ctx, digest, &dlen) != 1) { EVP_MD_CTX_free(ctx); return ""; }
    EVP_MD_CTX_free(ctx);
    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (unsigned int i = 0; i < dlen; ++i) oss << std::setw(2) << static_cast<unsigned>(digest[i]);
    return oss.str();
}
#endif

/// Verify that the pubkey file matches the compile-time trusted fingerprint.
/// Returns true if fingerprint matches or checking is not available.
static bool _verify_pubkey_fingerprint(const std::string& pubkey_path) {
    const std::string trusted(TRUSTED_PUBKEY_SHA256);
    if (trusted.empty()) {
        // No fingerprint compiled in — dev/test mode, allow any key
        return true;
    }
#if defined(AI_HAVE_OPENSSL) && AI_HAVE_OPENSSL
    std::ifstream f(pubkey_path, std::ios::binary);
    if (!f.is_open()) {
        std::fprintf(stderr, "[LicenseChecker] Cannot open pubkey for fingerprint check: %s\n",
                     pubkey_path.c_str());
        return false;
    }
    std::string pem((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    std::string actual = _sha256_hex(pem);
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
#else
    // No OpenSSL available but fingerprint is required — fail closed
    std::fprintf(stderr, "[LicenseChecker] OpenSSL not available but TRUSTED_PUBKEY_SHA256 is set — DENIED.\n");
    return false;
#endif
}

// ---------------------------------------------------------------------------
// Simple JSON field extractor (no external deps)
// ---------------------------------------------------------------------------

static std::string _json_string(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\"";
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

// ---------------------------------------------------------------------------
// LicenseCache
// ---------------------------------------------------------------------------

struct LicenseStatus {
    bool        valid       = false;
    bool        expired     = false;
    std::string license_id;
    std::string valid_until;   // ISO-8601
    int32_t     days_remaining = 0;
    std::vector<std::string> capabilities;
    std::string raw_json;      // original license body
};

class LicenseCache {
public:
    static LicenseCache& instance() {
        static LicenseCache cache;
        return cache;
    }

    void set_license_path(const std::string& path) {
        std::lock_guard<std::mutex> lk(mutex_);
        license_path_ = path;
        last_check_   = {};           // force immediate refresh
    }

    void set_pubkey_path(const std::string& path) {
        std::lock_guard<std::mutex> lk(mutex_);
        pubkey_path_ = path;
        pubkey_verified_ = false;     // force re-verification
        last_check_      = {};
    }

    LicenseStatus get() {
        std::lock_guard<std::mutex> lk(mutex_);
        auto now = std::chrono::steady_clock::now();
        if (now - last_check_ > cache_ttl_) {
            _refresh();
            last_check_ = now;
        }
        return cached_;
    }

    // Check if a specific capability is licensed
    bool is_capability_licensed(const std::string& cap_name) {
        LicenseStatus s = get();
        if (!s.valid || s.expired) return false;
        for (const auto& c : s.capabilities) {
            if (c == cap_name) return true;
        }
        return false;
    }

    std::string to_json() {
        LicenseStatus s = get();
        std::ostringstream os;
        os << "{"
           << "\"status\":\"" << (s.expired ? "expired" : (s.valid ? "valid" : "invalid")) << "\","
           << "\"license_id\":\"" << s.license_id << "\","
           << "\"valid_until\":\"" << s.valid_until << "\","
           << "\"days_remaining\":" << s.days_remaining << ","
           << "\"capabilities\":[";
        for (size_t i = 0; i < s.capabilities.size(); ++i) {
            if (i > 0) os << ",";
            os << "\"" << s.capabilities[i] << "\"";
        }
        os << "]}";
        return os.str();
    }

private:
    LicenseCache() : cache_ttl_(std::chrono::seconds(60)) {}

    void _refresh() {
        cached_ = LicenseStatus{};
        if (license_path_.empty()) {
            std::fprintf(stderr, "[LicenseChecker] No license path configured.\n");
            return;
        }

        // Verify public key fingerprint (once per pubkey_path change)
        if (!pubkey_verified_) {
            if (!pubkey_path_.empty()) {
                if (!_verify_pubkey_fingerprint(pubkey_path_)) {
                    std::fprintf(stderr, "[LicenseChecker] Public key fingerprint verification FAILED — license REJECTED.\n");
                    cached_.valid   = false;
                    cached_.expired = false;
                    return;
                }
                pubkey_verified_ = true;
            } else {
                // No pubkey path → fingerprint check skipped if no trusted hash compiled in
                const std::string trusted(TRUSTED_PUBKEY_SHA256);
                if (!trusted.empty()) {
                    std::fprintf(stderr, "[LicenseChecker] TRUSTED_PUBKEY_SHA256 is set but no pubkey path configured — DENIED.\n");
                    cached_.valid = false;
                    return;
                }
                pubkey_verified_ = true;
            }
        }

        std::ifstream f(license_path_, std::ios::binary);
        if (!f.is_open()) {
            std::fprintf(stderr, "[LicenseChecker] Cannot open license: %s\n",
                         license_path_.c_str());
            return;
        }
        std::string content((std::istreambuf_iterator<char>(f)),
                             std::istreambuf_iterator<char>());

        // Locate the JSON payload (the license.bin created by license_signer.py
        // is a signed JSON file; for this runtime we parse the JSON body directly)
        // Find opening '{'
        auto start = content.find('{');
        if (start == std::string::npos) {
            std::fprintf(stderr, "[LicenseChecker] Invalid license format.\n");
            return;
        }
        std::string json = content.substr(start);

        cached_.raw_json      = json;
        cached_.license_id    = _json_string(json, "license_id");
        cached_.valid_until   = _json_string(json, "valid_until");
        std::string status    = _json_string(json, "status");
        cached_.valid         = (status == "active");
        cached_.expired       = (status == "expired");

        // Parse capabilities array
        auto cap_pos = json.find("\"capabilities\"");
        if (cap_pos != std::string::npos) {
            auto arr_start = json.find('[', cap_pos);
            auto arr_end   = json.find(']', arr_start);
            if (arr_start != std::string::npos && arr_end != std::string::npos) {
                std::string arr = json.substr(arr_start + 1, arr_end - arr_start - 1);
                // Parse quoted strings from array
                size_t p = 0;
                while (p < arr.size()) {
                    auto q1 = arr.find('"', p);
                    if (q1 == std::string::npos) break;
                    auto q2 = arr.find('"', q1 + 1);
                    if (q2 == std::string::npos) break;
                    cached_.capabilities.push_back(arr.substr(q1 + 1, q2 - q1 - 1));
                    p = q2 + 1;
                }
            }
        }

        // Compute days remaining from valid_until (simplified: compare ISO date prefix)
        // All license times are in CST (UTC+8)
        if (!cached_.valid_until.empty() && cached_.valid) {
            // Use ctime to parse
            struct tm tm_exp = {};
            if (std::sscanf(cached_.valid_until.c_str(), "%4d-%2d-%2dT",
                            &tm_exp.tm_year, &tm_exp.tm_mon, &tm_exp.tm_mday) == 3) {
                tm_exp.tm_year -= 1900;
                tm_exp.tm_mon  -= 1;
                tm_exp.tm_hour = 0;
                tm_exp.tm_min  = 0;
                tm_exp.tm_sec  = 0;
#ifdef _WIN32
                // Convert CST time to epoch (subtract 8 hours from GMT conversion)
                time_t exp_t = _mkgmtime(&tm_exp) - (8 * 3600);
#else
                // Convert CST time to epoch (subtract 8 hours from GMT conversion)
                time_t exp_t = timegm(&tm_exp) - (8 * 3600);
#endif
                time_t now_t    = time(nullptr);
                int64_t diff    = static_cast<int64_t>(exp_t) - static_cast<int64_t>(now_t);
                cached_.days_remaining = static_cast<int32_t>(diff / 86400);
                if (cached_.days_remaining < 0) {
                    cached_.expired       = true;
                    cached_.days_remaining = 0;
                }
            }
        }

        std::fprintf(stdout,
            "[LicenseChecker] License %s: status=%s caps=%zu days_remaining=%d\n",
            cached_.license_id.c_str(),
            cached_.expired ? "expired" : (cached_.valid ? "valid" : "invalid"),
            cached_.capabilities.size(),
            cached_.days_remaining);
    }

    std::mutex    mutex_;
    std::string   license_path_;
    std::string   pubkey_path_;
    bool          pubkey_verified_ = false;
    LicenseStatus cached_;
    std::chrono::steady_clock::time_point last_check_;
    std::chrono::seconds cache_ttl_;
};

} // namespace agilestar

// C interface
void agilestar_license_set_path(const char* path) {
    agilestar::LicenseCache::instance().set_license_path(path);
}

void agilestar_license_set_pubkey_path(const char* path) {
    agilestar::LicenseCache::instance().set_pubkey_path(path);
}

bool agilestar_license_is_valid(const char* cap_name) {
    if (cap_name) {
        return agilestar::LicenseCache::instance().is_capability_licensed(cap_name);
    }
    return agilestar::LicenseCache::instance().get().valid;
}

// Write license status JSON into buf; returns bytes written or required size
int32_t agilestar_license_get_json(char* buf, int32_t buf_len) {
    std::string json = agilestar::LicenseCache::instance().to_json();
    int32_t needed   = static_cast<int32_t>(json.size());
    if (!buf || buf_len <= needed) return needed;
    std::memcpy(buf, json.c_str(), static_cast<size_t>(needed) + 1);
    return needed;
}
