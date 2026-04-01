/**
 * fingerprint.cpp
 * Machine fingerprint collection.
 *
 * Linux: reads DMI product_serial, product_uuid, and the first non-loopback
 *        NIC MAC address, concatenates them with '|', then SHA-256 hashes the
 *        result and returns "sha256:<hex>".
 * Windows: returns a placeholder ("sha256:windows-not-implemented").
 */

#include "fingerprint.h"

#include <openssl/evp.h>

#include <cstring>
#include <iomanip>
#include <sstream>
#include <string>

#ifdef _WIN32

std::string collect_fingerprint()
{
    return "sha256:windows-not-implemented";
}

#else  /* Linux / POSIX */

#include <dirent.h>
#include <fstream>

namespace {

// Read a single-line text file; return empty string on any error.
std::string read_file_trimmed(const std::string& path)
{
    std::ifstream f(path);
    if (!f.is_open()) {
        return "";
    }
    std::string line;
    std::getline(f, line);
    // Trim trailing whitespace / newlines
    while (!line.empty() && (line.back() == '\n' || line.back() == '\r' ||
                              line.back() == ' ')) {
        line.pop_back();
    }
    return line;
}

// Return the MAC address of the first non-loopback network interface found
// under /sys/class/net/, or empty string if none found.
std::string first_nic_mac()
{
    const char* net_path = "/sys/class/net";
    DIR*        dir      = opendir(net_path);
    if (!dir) {
        return "";
    }

    std::string mac;
    struct dirent* entry = nullptr;
    while ((entry = readdir(dir)) != nullptr) {
        const std::string iface = entry->d_name;
        if (iface == "." || iface == ".." || iface == "lo") {
            continue;
        }
        const std::string addr_path = std::string(net_path) + "/" + iface + "/address";
        const std::string candidate = read_file_trimmed(addr_path);
        if (!candidate.empty()) {
            mac = candidate;
            break;
        }
    }
    closedir(dir);
    return mac;
}

// SHA-256 hash of input; returns raw 32-byte digest.
std::string sha256_raw(const std::string& input)
{
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) {
        return "";
    }

    const EVP_MD* md = EVP_sha256();
    if (EVP_DigestInit_ex(ctx, md, nullptr) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }
    if (EVP_DigestUpdate(ctx, input.data(), input.size()) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }

    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int  digest_len = 0;
    if (EVP_DigestFinal_ex(ctx, digest, &digest_len) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }
    EVP_MD_CTX_free(ctx);

    return std::string(reinterpret_cast<char*>(digest),
                       static_cast<size_t>(digest_len));
}

// Hex-encode a raw byte string.
std::string hex_encode(const std::string& raw)
{
    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (unsigned char c : raw) {
        oss << std::setw(2) << static_cast<unsigned int>(c);
    }
    return oss.str();
}

}  // namespace

std::string collect_fingerprint()
{
    const std::string serial =
        read_file_trimmed("/sys/class/dmi/id/product_serial");
    const std::string uuid =
        read_file_trimmed("/sys/class/dmi/id/product_uuid");
    const std::string mac = first_nic_mac();

    const std::string combined = serial + "|" + uuid + "|" + mac;

    const std::string raw_hash = sha256_raw(combined);
    if (raw_hash.empty()) {
        return "sha256:error";
    }
    return "sha256:" + hex_encode(raw_hash);
}

#endif  /* _WIN32 */
