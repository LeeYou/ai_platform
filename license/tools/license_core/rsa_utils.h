#ifndef AGILESTAR_RSA_UTILS_H
#define AGILESTAR_RSA_UTILS_H

/**
 * rsa_utils.h
 * RSA-2048 key generation, signing, and verification using OpenSSL 3.x EVP API.
 */

#include <string>

/// Generates an RSA-2048 key pair; writes PEM files to the given paths.
/// Returns true on success.
bool generate_keypair(const std::string& privkey_path,
                      const std::string& pubkey_path);

/// Signs `data` with the PEM-encoded private key.
/// Returns a base64-encoded RSA-SHA256 signature, or empty string on error.
std::string rsa_sign(const std::string& privkey_pem,
                     const std::string& data);

/// Verifies `base64_signature` (RSA-SHA256) over `data` using the PEM-encoded
/// public key. Returns true if the signature is valid.
bool rsa_verify(const std::string& pubkey_pem,
                const std::string& data,
                const std::string& base64_signature);

#endif /* AGILESTAR_RSA_UTILS_H */
