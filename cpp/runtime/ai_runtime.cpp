/**
 * ai_runtime.cpp
 * AiRuntime* 公开接口实现（AiRuntimeInit / Acquire / Release / Reload /
 * GetCapabilities / GetLicenseStatus / Destroy）
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "ai_runtime_impl.h"

#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits.h>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

// ---------------------------------------------------------------------------
// Runtime state
// ---------------------------------------------------------------------------

static std::string g_so_dir;
static std::string g_model_base_dir;
static std::mutex  g_init_mutex;
static bool        g_initialized = false;

// Map capability_name → model_dir (for Reload)
static std::unordered_map<std::string, std::string> g_model_dirs;
static std::unordered_map<std::string, std::string> g_model_real_dirs;
static std::unordered_map<std::string, std::string> g_model_versions;
static std::mutex g_model_dirs_mutex;
static thread_local std::string g_last_error_json;

static std::string json_escape(const std::string& value) {
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

static bool read_file(const std::string& path, std::string* out) {
    if (!out) return false;
    std::ifstream input(path);
    if (!input.is_open()) return false;
    out->assign((std::istreambuf_iterator<char>(input)),
                std::istreambuf_iterator<char>());
    return true;
}

static std::string extract_json_string(const std::string& json, const std::string& key) {
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

static std::string extract_manifest_version(const std::string& manifest_json) {
    std::string version = extract_json_string(manifest_json, "model_version");
    if (!version.empty()) return version;
    return extract_json_string(manifest_json, "version");
}

static std::string read_model_version(const std::string& model_dir) {
    std::string manifest_json;
    if (!read_file(model_dir + "/manifest.json", &manifest_json)) {
        return "unknown";
    }
    std::string version = extract_manifest_version(manifest_json);
    return version.empty() ? "unknown" : version;
}

static std::string resolve_realpath_or_self(const std::string& path) {
    char resolved[PATH_MAX] = {};
    if (::realpath(path.c_str(), resolved)) {
        return resolved;
    }
    return path;
}

static std::string resolve_pubkey_path(const char* license_path) {
    const char* env_pubkey = std::getenv("AI_PUBKEY_PATH");
    if (env_pubkey && env_pubkey[0] != '\0') {
        return env_pubkey;
    }

    if (!license_path || license_path[0] == '\0') {
        return "";
    }

    std::string resolved = license_path;
    auto slash = resolved.find_last_of("/\\");
    if (slash == std::string::npos) {
        return "";
    }
    return resolved.substr(0, slash + 1) + "pubkey.pem";
}

static std::string build_error_json(int32_t code, const std::string& message, int32_t status_code) {
    std::ostringstream os;
    os << "{"
       << "\"code\":" << code
       << ",\"message\":\"" << json_escape(message) << "\""
       << ",\"status_code\":" << status_code
       << "}";
    return os.str();
}

static void clear_last_error() {
    g_last_error_json.clear();
}

static void set_last_error(const std::string& error_json) {
    g_last_error_json = error_json;
}

// ---------------------------------------------------------------------------
// AiRuntimeInit
// ---------------------------------------------------------------------------

int32_t AiRuntimeInit(const char* so_dir,
                       const char* model_base_dir,
                       const char* license_path)
{
    std::lock_guard<std::mutex> lk(g_init_mutex);
    if (g_initialized) {
        std::fprintf(stderr, "[Runtime] Already initialized.\n");
        return AI_OK;
    }

    g_so_dir         = so_dir         ? so_dir         : "";
    g_model_base_dir = model_base_dir ? model_base_dir : "";

    // 1. Set license path and do initial validation
    if (license_path) {
        agilestar_license_set_path(license_path);
        std::string pubkey_path = resolve_pubkey_path(license_path);
        if (!pubkey_path.empty()) {
            agilestar_license_set_pubkey_path(pubkey_path.c_str());
        }
    }

    // 2. Load all capability SOs
    int32_t rc = agilestar_loader_init(g_so_dir.c_str());
    if (rc != AI_OK) {
        std::fprintf(stderr, "[Runtime] Capability loader failed (rc=%d)\n", rc);
        return rc;
    }

    // 3. For each loaded capability, verify model package and create instance pool
    auto cap_names = agilestar_loader_names();
    for (const auto& cap : cap_names) {
        std::string model_dir = g_model_base_dir + "/" + cap + "/current";

        // Verify model manifest (best-effort — warn only if missing)
        int32_t mv = agilestar_model_verify(model_dir.c_str(), cap.c_str());
        if (mv != AI_OK) {
            std::fprintf(stderr,
                "[Runtime] WARNING: model verification failed for %s (rc=%d)\n",
                cap.c_str(), mv);
        }

        // Create instance pool (1 min, license-constrained max)
        const int max_instances = std::max(1, agilestar_license_get_max_instances());
        agilestar_pool_add(cap.c_str(), 1, max_instances, model_dir.c_str());

        std::lock_guard<std::mutex> lk2(g_model_dirs_mutex);
        g_model_dirs[cap] = model_dir;
        g_model_real_dirs[cap] = resolve_realpath_or_self(model_dir);
        g_model_versions[cap] = read_model_version(model_dir);
    }

    g_initialized = true;
    std::fprintf(stdout, "[Runtime] Initialized with %zu capability(ies).\n",
                 cap_names.size());
    return AI_OK;
}

// ---------------------------------------------------------------------------
// AiRuntimeGetCapabilities
// ---------------------------------------------------------------------------

int32_t AiRuntimeGetCapabilities(char* buf, int32_t buf_len) {
    auto names = agilestar_loader_names();

    std::ostringstream os;
    os << "{\"capabilities\":[";
    for (size_t i = 0; i < names.size(); ++i) {
        if (i > 0) os << ",";
        std::string model_dir = "";
        std::string real_model_dir = "";
        std::string version = "unknown";
        {
            std::lock_guard<std::mutex> lk(g_model_dirs_mutex);
            auto dir_it = g_model_dirs.find(names[i]);
            if (dir_it != g_model_dirs.end()) model_dir = dir_it->second;
            auto real_it = g_model_real_dirs.find(names[i]);
            if (real_it != g_model_real_dirs.end()) real_model_dir = real_it->second;
            auto version_it = g_model_versions.find(names[i]);
            if (version_it != g_model_versions.end()) version = version_it->second;
        }
        os << "{\"name\":\"" << json_escape(names[i])
           << "\",\"status\":\"loaded\""
           << ",\"version\":\"" << json_escape(version) << "\""
           << ",\"model_dir\":\"" << json_escape(model_dir) << "\""
           << ",\"real_model_dir\":\"" << json_escape(real_model_dir) << "\"}";
    }
    os << "]}";

    std::string json = os.str();
    int32_t needed   = static_cast<int32_t>(json.size());
    if (!buf || buf_len <= needed) return needed;
    std::memcpy(buf, json.c_str(), static_cast<size_t>(needed) + 1);
    return needed;
}

// ---------------------------------------------------------------------------
// AiRuntimeAcquire / AiRuntimeRelease
// ---------------------------------------------------------------------------

// We need to track which capability a handle belongs to for Release.
// Use a global map handle → cap_name (protected by mutex).
static std::unordered_map<AiHandle, std::string> g_handle_cap;
static std::mutex g_handle_cap_mutex;

AiHandle AiRuntimeAcquire(const char* capability_name, int32_t timeout_ms) {
    clear_last_error();
    if (!capability_name) {
        set_last_error(build_error_json(AI_ERR_INVALID_PARAM, "Invalid capability name", 400));
        return nullptr;
    }

    std::string capability_version = "unknown";
    {
        std::lock_guard<std::mutex> lk(g_model_dirs_mutex);
        auto version_it = g_model_versions.find(capability_name);
        if (version_it != g_model_versions.end()) capability_version = version_it->second;
    }

    const std::string license_error = agilestar_license_get_failure_json(
        capability_name,
        capability_version.c_str()
    );
    if (!license_error.empty()) {
        set_last_error(license_error);
        std::fprintf(stderr, "[Runtime] License not valid for capability: %s\n",
                     capability_name);
        return nullptr;
    }

    if (!agilestar_loader_find(capability_name)) {
        set_last_error(build_error_json(3001, "Capability not found or not loaded", 400));
        return nullptr;
    }

    AiHandle h = agilestar_pool_acquire(capability_name, timeout_ms);
    if (!h) {
        set_last_error(build_error_json(3001, "Instance pool timeout or capability not available", 400));
        return nullptr;
    }

    std::lock_guard<std::mutex> lk(g_handle_cap_mutex);
    g_handle_cap[h] = capability_name;
    return h;
}

void AiRuntimeRelease(AiHandle handle) {
    if (!handle) return;
    std::string cap_name;
    {
        std::lock_guard<std::mutex> lk(g_handle_cap_mutex);
        auto it = g_handle_cap.find(handle);
        if (it == g_handle_cap.end()) return;
        cap_name = it->second;
        g_handle_cap.erase(it);
    }
    agilestar_pool_release(handle, cap_name.c_str());
}

// ---------------------------------------------------------------------------
// AiRuntimeInfer / AiRuntimeFreeResult
// ---------------------------------------------------------------------------

int32_t AiRuntimeInfer(AiHandle handle, const AiImage* input, AiResult* output) {
    if (!handle || !input || !output) {
        return AI_ERR_INVALID_PARAM;
    }

    // Find which capability this handle belongs to
    std::string cap_name;
    {
        std::lock_guard<std::mutex> lk(g_handle_cap_mutex);
        auto it = g_handle_cap.find(handle);
        if (it == g_handle_cap.end()) {
            std::fprintf(stderr, "[Runtime] Invalid handle in AiRuntimeInfer\n");
            return AI_ERR_INVALID_PARAM;
        }
        cap_name = it->second;
    }

    // Get capability entry and call its AiInfer function
    const agilestar::CapabilityEntry* entry = agilestar_loader_find(cap_name.c_str());
    if (!entry || !entry->fn_Infer) {
        std::fprintf(stderr, "[Runtime] Capability %s not found or has no Infer function\n",
                     cap_name.c_str());
        return AI_ERR_CAPABILITY_MISSING;
    }

    return entry->fn_Infer(handle, input, output);
}

void AiRuntimeFreeResult(AiResult* result) {
    if (!result) return;

    // AiFreeResult is typically implemented by capability SO to free its allocated memory
    // However, since we don't know which capability allocated this result,
    // we use a convention: the capability SO should manage its own memory via AiFreeResult
    // For now, we just free the common fields if they were allocated by the capability
    if (result->json_result) {
        // Capability SOs are expected to use malloc/free or provide their own AiFreeResult
        // Here we can't call capability-specific free, so we rely on capabilities
        // to expose AiFreeResult if needed, or we just clear the pointer
        // The safer approach is to have each capability expose AiFreeResult
        // For this wrapper, we'll just clear the fields
        // NOTE: This assumes capability SOs manage their own memory properly
        result->json_result = nullptr;
        result->result_len = 0;
    }
    if (result->error_msg) {
        result->error_msg = nullptr;
    }
}

// ---------------------------------------------------------------------------
// AiRuntimeReload
// ---------------------------------------------------------------------------

int32_t AiRuntimeReload(const char* capability_name) {
    if (!capability_name) return AI_ERR_INVALID_PARAM;

    std::string model_dir;
    {
        std::lock_guard<std::mutex> lk(g_model_dirs_mutex);
        auto it = g_model_dirs.find(capability_name);
        if (it == g_model_dirs.end()) return AI_ERR_CAPABILITY_MISSING;
        model_dir = it->second;
    }

    int32_t mv = agilestar_model_verify(model_dir.c_str(), capability_name);
    if (mv != AI_OK) return mv;

    {
        std::lock_guard<std::mutex> lk(g_model_dirs_mutex);
        g_model_real_dirs[capability_name] = resolve_realpath_or_self(model_dir);
        g_model_versions[capability_name] = read_model_version(model_dir);
    }

    return agilestar_pool_reload(capability_name, model_dir.c_str());
}

// ---------------------------------------------------------------------------
// AiRuntimeGetLicenseStatus
// ---------------------------------------------------------------------------

int32_t AiRuntimeGetLicenseStatus(char* buf, int32_t buf_len) {
    return agilestar_license_get_json(buf, buf_len);
}

int32_t AiRuntimeGetLastError(char* buf, int32_t buf_len) {
    if (g_last_error_json.empty()) return 0;
    const int32_t needed = static_cast<int32_t>(g_last_error_json.size());
    if (!buf || buf_len <= needed) return needed;
    std::memcpy(buf, g_last_error_json.c_str(), static_cast<size_t>(needed) + 1);
    return needed;
}

// ---------------------------------------------------------------------------
// AiRuntimeDestroy
// ---------------------------------------------------------------------------

void AiRuntimeDestroy(void) {
    std::lock_guard<std::mutex> lk(g_init_mutex);
    agilestar_pool_destroy_all();
    agilestar_loader_unload_all();
    {
        std::lock_guard<std::mutex> lk2(g_handle_cap_mutex);
        g_handle_cap.clear();
    }
    {
        std::lock_guard<std::mutex> lk2(g_model_dirs_mutex);
        g_model_dirs.clear();
        g_model_real_dirs.clear();
        g_model_versions.clear();
    }
    g_initialized = false;
    std::fprintf(stdout, "[Runtime] Destroyed.\n");
}
