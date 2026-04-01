/**
 * main.cpp
 * license_tool CLI
 *
 * Subcommands:
 *   fingerprint
 *   keygen   --privkey <path> --pubkey <path>
 *   sign     --privkey <path> --input <path> --output <path>
 *   verify   --pubkey <path> --license <path>
 *                [--fingerprint <sha256:...>] [--capability <name>]
 */

#include "license_core.h"

#include <cstring>
#include <iostream>
#include <string>
#include <unordered_map>

// ---------------------------------------------------------------------------
// Argument parsing helper
// ---------------------------------------------------------------------------
namespace {

struct Args {
    std::unordered_map<std::string, std::string> flags;

    bool has(const std::string& key) const
    {
        return flags.count(key) != 0;
    }

    std::string get(const std::string& key,
                    const std::string& default_val = "") const
    {
        auto it = flags.find(key);
        return (it != flags.end()) ? it->second : default_val;
    }
};

Args parse_args(int argc, char* argv[], int start)
{
    Args args;
    for (int i = start; i < argc; ++i) {
        const std::string token = argv[i];
        if (token.size() > 2 && token.substr(0, 2) == "--") {
            const std::string key = token.substr(2);
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                args.flags[key] = argv[i + 1];
                ++i;
            } else {
                args.flags[key] = "";  // flag without value
            }
        }
    }
    return args;
}

void usage(const char* prog)
{
    std::cerr
        << "Usage:\n"
        << "  " << prog << " fingerprint\n"
        << "  " << prog << " keygen   --privkey <path> --pubkey <path>\n"
        << "  " << prog << " sign     --privkey <path> --input <path> --output <path>\n"
        << "  " << prog << " verify   --pubkey <path> --license <path>\n"
        << "                         [--fingerprint <sha256:...>]\n"
        << "                         [--capability <name>]\n";
}

}  // namespace

// ---------------------------------------------------------------------------
// Subcommand handlers
// ---------------------------------------------------------------------------

static int cmd_fingerprint()
{
    std::cout << collect_fingerprint() << "\n";
    return 0;
}

static int cmd_keygen(const Args& args)
{
    if (!args.has("privkey") || !args.has("pubkey")) {
        std::cerr << "keygen requires --privkey and --pubkey\n";
        return 1;
    }
    if (!generate_keypair(args.get("privkey"), args.get("pubkey"))) {
        std::cerr << "keygen failed\n";
        return 1;
    }
    std::cout << "Key pair written:\n"
              << "  private: " << args.get("privkey") << "\n"
              << "  public:  " << args.get("pubkey")  << "\n";
    return 0;
}

static int cmd_sign(const Args& args)
{
    if (!args.has("privkey") || !args.has("input") || !args.has("output")) {
        std::cerr << "sign requires --privkey, --input, and --output\n";
        return 1;
    }

    LicenseData ld;
    if (!load_license(args.get("input"), ld)) {
        std::cerr << "Failed to parse license template: " << args.get("input") << "\n";
        return 1;
    }

    if (!generate_license(ld, args.get("privkey"), args.get("output"))) {
        std::cerr << "sign failed\n";
        return 1;
    }

    std::cout << "Signed license written to: " << args.get("output") << "\n";
    return 0;
}

static int cmd_verify(const Args& args)
{
    if (!args.has("pubkey") || !args.has("license")) {
        std::cerr << "verify requires --pubkey and --license\n";
        return 1;
    }

    const VerifyResult result = verify_license(
        args.get("license"),
        args.get("pubkey"),
        args.get("fingerprint"),
        args.get("capability"));

    if (result == VerifyResult::OK) {
        std::cout << "License OK\n";
        return 0;
    }

    std::cerr << "License verification failed: " << verify_result_str(result) << "\n";
    return static_cast<int>(result);
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

int main(int argc, char* argv[])
{
    if (argc < 2) {
        usage(argv[0]);
        return 1;
    }

    const std::string subcmd = argv[1];
    const Args args = parse_args(argc, argv, 2);

    if (subcmd == "fingerprint") return cmd_fingerprint();
    if (subcmd == "keygen")      return cmd_keygen(args);
    if (subcmd == "sign")        return cmd_sign(args);
    if (subcmd == "verify")      return cmd_verify(args);

    std::cerr << "Unknown subcommand: " << subcmd << "\n";
    usage(argv[0]);
    return 1;
}
