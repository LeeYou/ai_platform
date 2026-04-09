/**
 * rsa_utils.cpp
 * RSA-2048 key generation, signing, and verification.
 * Uses the OpenSSL 3.x EVP API exclusively (no deprecated calls).
 */

#include "rsa_utils.h"

#include <openssl/bio.h>
#include <openssl/evp.h>
#include <openssl/pem.h>
#include <openssl/rsa.h>

#include <cstring>
#include <memory>
#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------
namespace {

// RAII wrapper for OpenSSL BIO.
struct BioDeleter {
    void operator()(BIO* b) const { BIO_free_all(b); }
};
using BioPtr = std::unique_ptr<BIO, BioDeleter>;

// RAII wrapper for EVP_PKEY.
struct PkeyDeleter {
    void operator()(EVP_PKEY* k) const { EVP_PKEY_free(k); }
};
using PkeyPtr = std::unique_ptr<EVP_PKEY, PkeyDeleter>;

// RAII wrapper for EVP_PKEY_CTX.
struct PkeyCtxDeleter {
    void operator()(EVP_PKEY_CTX* c) const { EVP_PKEY_CTX_free(c); }
};
using PkeyCtxPtr = std::unique_ptr<EVP_PKEY_CTX, PkeyCtxDeleter>;

// RAII wrapper for EVP_MD_CTX.
struct MdCtxDeleter {
    void operator()(EVP_MD_CTX* c) const { EVP_MD_CTX_free(c); }
};
using MdCtxPtr = std::unique_ptr<EVP_MD_CTX, MdCtxDeleter>;

// Base64-encode raw bytes using OpenSSL BIO chain (no newlines).
std::string base64_encode(const unsigned char* data, size_t len)
{
    BioPtr b64(BIO_new(BIO_f_base64()));
    if (!b64) return "";

    BIO_set_flags(b64.get(), BIO_FLAGS_BASE64_NO_NL);

    BIO* mem_raw = BIO_new(BIO_s_mem());
    if (!mem_raw) return "";

    // b64 now owns mem_raw
    BIO_push(b64.get(), mem_raw);

    BIO_write(b64.get(), data, static_cast<int>(len));
    BIO_flush(b64.get());

    BUF_MEM* buf = nullptr;
    BIO_get_mem_ptr(b64.get(), &buf);

    return std::string(buf->data, buf->length);
}

// Base64-decode a string; returns empty vector on error.
std::vector<unsigned char> base64_decode(const std::string& encoded)
{
    BioPtr b64(BIO_new(BIO_f_base64()));
    if (!b64) return {};

    BIO_set_flags(b64.get(), BIO_FLAGS_BASE64_NO_NL);

    BIO* mem_raw = BIO_new_mem_buf(encoded.data(),
                                   static_cast<int>(encoded.size()));
    if (!mem_raw) return {};

    // b64 now owns mem_raw
    BIO_push(b64.get(), mem_raw);

    std::vector<unsigned char> out(encoded.size());
    int n = BIO_read(b64.get(), out.data(), static_cast<int>(out.size()));
    if (n <= 0) return {};

    out.resize(static_cast<size_t>(n));
    return out;
}

// Load EVP_PKEY from a PEM string (private or public).
PkeyPtr load_private_key(const std::string& pem)
{
    BioPtr bio(BIO_new_mem_buf(pem.data(), static_cast<int>(pem.size())));
    if (!bio) return nullptr;
    return PkeyPtr(PEM_read_bio_PrivateKey(bio.get(), nullptr, nullptr, nullptr));
}

PkeyPtr load_public_key(const std::string& pem)
{
    BioPtr bio(BIO_new_mem_buf(pem.data(), static_cast<int>(pem.size())));
    if (!bio) return nullptr;
    return PkeyPtr(PEM_read_bio_PUBKEY(bio.get(), nullptr, nullptr, nullptr));
}

// Write a string to a file.
bool write_file(const std::string& path, const std::string& content)
{
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) return false;
    fwrite(content.data(), 1, content.size(), f);
    fclose(f);
    return true;
}

}  // namespace

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

bool generate_keypair(const std::string& privkey_path,
                      const std::string& pubkey_path)
{
    // Create keygen context for RSA
    PkeyCtxPtr ctx(EVP_PKEY_CTX_new_from_name(nullptr, "RSA", nullptr));
    if (!ctx) return false;

    if (EVP_PKEY_keygen_init(ctx.get()) <= 0) return false;

    // Set key size to 2048 bits
    if (EVP_PKEY_CTX_set_rsa_keygen_bits(ctx.get(), 2048) <= 0) return false;

    EVP_PKEY* raw_key = nullptr;
    if (EVP_PKEY_keygen(ctx.get(), &raw_key) <= 0) return false;
    PkeyPtr key(raw_key);

    // Write private key PEM
    {
        BioPtr bio(BIO_new(BIO_s_mem()));
        if (!bio) return false;
        if (PEM_write_bio_PrivateKey(bio.get(), key.get(), nullptr,
                                     nullptr, 0, nullptr, nullptr) != 1) {
            return false;
        }
        BUF_MEM* buf = nullptr;
        BIO_get_mem_ptr(bio.get(), &buf);
        if (!write_file(privkey_path, std::string(buf->data, buf->length))) {
            return false;
        }
    }

    // Write public key PEM
    {
        BioPtr bio(BIO_new(BIO_s_mem()));
        if (!bio) return false;
        if (PEM_write_bio_PUBKEY(bio.get(), key.get()) != 1) return false;
        BUF_MEM* buf = nullptr;
        BIO_get_mem_ptr(bio.get(), &buf);
        if (!write_file(pubkey_path, std::string(buf->data, buf->length))) {
            return false;
        }
    }

    return true;
}

std::string rsa_sign(const std::string& privkey_pem, const std::string& data)
{
    PkeyPtr key = load_private_key(privkey_pem);
    if (!key) return "";

    MdCtxPtr md_ctx(EVP_MD_CTX_new());
    if (!md_ctx) return "";

    EVP_PKEY_CTX* pkey_ctx = nullptr;
    if (EVP_DigestSignInit(md_ctx.get(), &pkey_ctx, EVP_sha256(),
                           nullptr, key.get()) != 1) {
        return "";
    }
    // RSA-PSS with SHA-256 MGF1 and maximum salt length — must match
    // Python: padding.PSS(mgf=MGF1(SHA256()), salt_length=PSS.MAX_LENGTH)
    // and the runtime verifier in license_checker.cpp.
    if (EVP_PKEY_CTX_set_rsa_padding(pkey_ctx, RSA_PKCS1_PSS_PADDING) != 1 ||
        EVP_PKEY_CTX_set_rsa_mgf1_md(pkey_ctx, EVP_sha256()) != 1 ||
        EVP_PKEY_CTX_set_rsa_pss_saltlen(pkey_ctx, RSA_PSS_SALTLEN_MAX_SIGN) != 1) {
        return "";
    }
    if (EVP_DigestSignUpdate(md_ctx.get(), data.data(), data.size()) != 1) {
        return "";
    }

    size_t sig_len = 0;
    if (EVP_DigestSignFinal(md_ctx.get(), nullptr, &sig_len) != 1) return "";

    std::vector<unsigned char> sig(sig_len);
    if (EVP_DigestSignFinal(md_ctx.get(), sig.data(), &sig_len) != 1) return "";
    sig.resize(sig_len);

    return base64_encode(sig.data(), sig.size());
}

bool rsa_verify(const std::string& pubkey_pem,
                const std::string& data,
                const std::string& base64_signature)
{
    PkeyPtr key = load_public_key(pubkey_pem);
    if (!key) return false;

    std::vector<unsigned char> sig = base64_decode(base64_signature);
    if (sig.empty()) return false;

    MdCtxPtr md_ctx(EVP_MD_CTX_new());
    if (!md_ctx) return false;

    EVP_PKEY_CTX* pkey_ctx = nullptr;
    if (EVP_DigestVerifyInit(md_ctx.get(), &pkey_ctx, EVP_sha256(),
                             nullptr, key.get()) != 1) {
        return false;
    }
    // RSA-PSS with SHA-256 MGF1 and auto salt length — accepts signatures
    // produced with any valid PSS salt length (including PSS.MAX_LENGTH from Python).
    if (EVP_PKEY_CTX_set_rsa_padding(pkey_ctx, RSA_PKCS1_PSS_PADDING) != 1 ||
        EVP_PKEY_CTX_set_rsa_mgf1_md(pkey_ctx, EVP_sha256()) != 1 ||
        EVP_PKEY_CTX_set_rsa_pss_saltlen(pkey_ctx, RSA_PSS_SALTLEN_AUTO) != 1) {
        return false;
    }
    if (EVP_DigestVerifyUpdate(md_ctx.get(), data.data(), data.size()) != 1) {
        return false;
    }

    return EVP_DigestVerifyFinal(md_ctx.get(), sig.data(), sig.size()) == 1;
}
