/**
 * capability_loader.cpp
 * 动态加载能力 SO（dlopen/dlsym），ABI 版本检查，能力注册表管理
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "ai_runtime_impl.h"

#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <dlfcn.h>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace agilestar {

// ---------------------------------------------------------------------------
// CapabilityRegistry — global table of loaded capabilities
// ---------------------------------------------------------------------------

class CapabilityRegistry {
public:
    static CapabilityRegistry& instance() {
        static CapabilityRegistry reg;
        return reg;
    }

    // Scan so_dir, dlopen each lib*.so, check ABI, register
    int load_from_dir(const std::string& so_dir) {
        std::lock_guard<std::mutex> lk(mutex_);
        DIR* dir = opendir(so_dir.c_str());
        if (!dir) {
            std::fprintf(stderr, "[CapabilityLoader] Cannot open SO dir: %s\n",
                         so_dir.c_str());
            return AI_ERR_LOAD_FAILED;
        }

        struct dirent* ent;
        while ((ent = readdir(dir)) != nullptr) {
            const char* name = ent->d_name;
            // Match lib*.so (and lib*.so.*)
            if (std::strncmp(name, "lib", 3) != 0) continue;
            const char* ext = std::strstr(name, ".so");
            if (!ext) continue;

            std::string path = so_dir + "/" + name;
            _try_load(path);
        }
        closedir(dir);
        return AI_OK;
    }

    const CapabilityEntry* find(const std::string& cap_name) const {
        std::lock_guard<std::mutex> lk(mutex_);
        auto it = entries_.find(cap_name);
        return it != entries_.end() ? &it->second : nullptr;
    }

    std::vector<std::string> capability_names() const {
        std::lock_guard<std::mutex> lk(mutex_);
        std::vector<std::string> names;
        names.reserve(entries_.size());
        for (auto& kv : entries_) names.push_back(kv.first);
        return names;
    }

    void unload_all() {
        std::lock_guard<std::mutex> lk(mutex_);
        for (auto& kv : entries_) {
            if (kv.second.dl_handle) dlclose(kv.second.dl_handle);
        }
        entries_.clear();
    }

private:
    CapabilityRegistry() = default;

    void _try_load(const std::string& path) {
        void* handle = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            std::fprintf(stderr, "[CapabilityLoader] dlopen failed: %s — %s\n",
                         path.c_str(), dlerror());
            return;
        }

        // Resolve AiGetAbiVersion first
        using GetVerFn = int32_t (*)();
        auto fn_ver = reinterpret_cast<GetVerFn>(dlsym(handle, "AiGetAbiVersion"));
        if (!fn_ver) {
            std::fprintf(stderr, "[CapabilityLoader] %s: AiGetAbiVersion not found\n",
                         path.c_str());
            dlclose(handle);
            return;
        }

        int32_t plugin_ver = fn_ver();
        int32_t runtime_major = AI_ABI_VERSION / 10000;
        int32_t plugin_major  = plugin_ver / 10000;
        if (plugin_major != runtime_major) {
            std::fprintf(stderr,
                "[CapabilityLoader] %s: ABI version mismatch "
                "(plugin=%d, runtime=%d) — skipping\n",
                path.c_str(), plugin_ver, AI_ABI_VERSION);
            dlclose(handle);
            return;
        }

        // Derive capability name from filename: libfoo.so → foo
        std::string basename = path.substr(path.rfind('/') + 1);
        // strip leading "lib"
        std::string cap_name = basename.substr(3);
        // strip ".so" suffix and everything after
        auto dot = cap_name.find(".so");
        if (dot != std::string::npos) cap_name = cap_name.substr(0, dot);

        // Resolve remaining symbols
        CapabilityEntry entry;
        entry.name        = cap_name;
        entry.so_path     = path;
        entry.dl_handle   = handle;
        entry.fn_GetAbiVersion = fn_ver;

#define RESOLVE(sym, field) \
        entry.field = reinterpret_cast<decltype(entry.field)>(dlsym(handle, sym)); \
        if (!entry.field) { \
            std::fprintf(stderr, "[CapabilityLoader] %s: symbol '%s' not found\n", \
                         path.c_str(), sym); \
            dlclose(handle); return; \
        }

        RESOLVE("AiCreate",     fn_Create)
        RESOLVE("AiInit",       fn_Init)
        RESOLVE("AiInfer",      fn_Infer)
        RESOLVE("AiReload",     fn_Reload)
        RESOLVE("AiGetInfo",    fn_GetInfo)
        RESOLVE("AiDestroy",    fn_Destroy)
        RESOLVE("AiFreeResult", fn_FreeResult)
#undef RESOLVE

        std::fprintf(stdout, "[CapabilityLoader] Loaded: %s (ABI v%d) from %s\n",
                     cap_name.c_str(), plugin_ver, path.c_str());

        entries_[cap_name] = std::move(entry);
    }

    mutable std::mutex mutex_;
    std::unordered_map<std::string, CapabilityEntry> entries_;
};

} // namespace agilestar

// ---------------------------------------------------------------------------
// C interface for runtime internals
// ---------------------------------------------------------------------------

int agilestar_loader_init(const char* so_dir) {
    return agilestar::CapabilityRegistry::instance().load_from_dir(so_dir);
}

const agilestar::CapabilityEntry* agilestar_loader_find(const char* name) {
    return agilestar::CapabilityRegistry::instance().find(name);
}

std::vector<std::string> agilestar_loader_names() {
    return agilestar::CapabilityRegistry::instance().capability_names();
}

void agilestar_loader_unload_all() {
    agilestar::CapabilityRegistry::instance().unload_all();
}
