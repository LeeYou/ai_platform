/**
 * model_loader.cpp
 * 模型包加载：读取 manifest.json、校验 checksum（SHA256）
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "ai_runtime_impl.h"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>

// Simple SHA-256 using OpenSSL (available on all target platforms)
#if __has_include(<openssl/evp.h>)
#  include <openssl/evp.h>
#  define HAS_OPENSSL_SHA 1
#else
#  define HAS_OPENSSL_SHA 0
#endif

namespace agilestar {

// ---------------------------------------------------------------------------
// ModelManifest
// ---------------------------------------------------------------------------

struct ModelManifest {
    std::string capability;
    std::string model_version;
    std::string model_file_checksum;  // "sha256:abcdef..."
};

// Minimal JSON string extractor (reuse same helper pattern)
static std::string _jstr(const std::string& json, const std::string& key) {
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

static std::string _manifest_version(const std::string& json) {
    std::string version = _jstr(json, "model_version");
    if (!version.empty()) return version;
    return _jstr(json, "version");
}

static std::string _jstr_nested(const std::string& json,
                                 const std::string& outer_key,
                                 const std::string& inner_key) {
    std::string needle = "\"" + outer_key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find('{', pos + needle.size());
    if (pos == std::string::npos) return "";
    auto end = json.find('}', pos);
    if (end == std::string::npos) return "";
    return _jstr(json.substr(pos, end - pos + 1), inner_key);
}

// ---------------------------------------------------------------------------
// SHA-256 helper
// ---------------------------------------------------------------------------

static std::string _sha256_hex(const std::string& path) {
#if HAS_OPENSSL_SHA
    std::ifstream f(path, std::ios::binary);
    if (!f.is_open()) return "";

    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) return "";
    if (EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }

    char buf[65536];
    while (f.read(buf, sizeof(buf)) || f.gcount() > 0) {
        if (EVP_DigestUpdate(ctx, buf, static_cast<size_t>(f.gcount())) != 1) {
            EVP_MD_CTX_free(ctx);
            return "";
        }
    }

    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int digest_len = 0;
    if (EVP_DigestFinal_ex(ctx, digest, &digest_len) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }
    EVP_MD_CTX_free(ctx);

    static constexpr char kHexDigits[] = "0123456789abcdef";
    std::string hex;
    hex.reserve(static_cast<size_t>(digest_len) * 2);
    for (unsigned int i = 0; i < digest_len; ++i) {
        const unsigned char byte = digest[i];
        hex.push_back(kHexDigits[byte >> 4]);
        hex.push_back(kHexDigits[byte & 0x0F]);
    }
    return hex;
#else
    (void)path;
    return "";  // checksum validation skipped — OpenSSL not available
#endif
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

int32_t load_and_verify_manifest(const std::string& model_dir,
                                  const std::string& expected_capability,
                                  ModelManifest*     out) {
    std::string manifest_path = model_dir + "/manifest.json";
    std::ifstream f(manifest_path);
    if (!f.is_open()) {
        std::fprintf(stderr, "[ModelLoader] Cannot open: %s\n", manifest_path.c_str());
        return AI_ERR_MODEL_CORRUPT;
    }

    std::string json((std::istreambuf_iterator<char>(f)),
                      std::istreambuf_iterator<char>());

    ModelManifest manifest;
    manifest.capability          = _jstr(json, "capability");
    manifest.model_version       = _manifest_version(json);
    manifest.model_file_checksum = _jstr_nested(json, "checksum", "model_file");

    // Validate capability name
    if (!expected_capability.empty() &&
        manifest.capability != expected_capability) {
        std::fprintf(stderr,
            "[ModelLoader] Capability mismatch: expected '%s', got '%s'\n",
            expected_capability.c_str(), manifest.capability.c_str());
        return AI_ERR_MODEL_CORRUPT;
    }

    // Validate checksum
    if (!manifest.model_file_checksum.empty() &&
        manifest.model_file_checksum.substr(0, 7) == "sha256:") {
        std::string expected_hash = manifest.model_file_checksum.substr(7);
        std::string model_path    = model_dir + "/model.onnx";
        std::string actual_hash   = _sha256_hex(model_path);

        if (!actual_hash.empty() && actual_hash != expected_hash) {
            std::fprintf(stderr,
                "[ModelLoader] Checksum mismatch for %s\n  expected: %s\n  actual:   %s\n",
                model_path.c_str(), expected_hash.c_str(), actual_hash.c_str());
            return AI_ERR_MODEL_CORRUPT;
        }
    }

    std::fprintf(stdout,
        "[ModelLoader] Manifest OK: %s v%s in %s\n",
        manifest.capability.c_str(), manifest.model_version.c_str(), model_dir.c_str());

    if (out) *out = std::move(manifest);
    return AI_OK;
}

} // namespace agilestar

// C interface
int32_t agilestar_model_verify(const char* model_dir,
                                const char* expected_capability) {
    return agilestar::load_and_verify_manifest(
        model_dir,
        expected_capability ? expected_capability : "",
        nullptr);
}
