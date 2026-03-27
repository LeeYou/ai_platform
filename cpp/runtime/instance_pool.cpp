/**
 * instance_pool.cpp
 * 推理实例池：Acquire / Release / 动态扩缩容 / 超时处理
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "ai_runtime_impl.h"

#include <cassert>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <cstdio>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

namespace agilestar {

// Forward declaration from capability_loader
struct CapabilityEntry;
const CapabilityEntry* agilestar_loader_find(const char* name);

// ---------------------------------------------------------------------------
// PoolEntry — one idle handle + which capability it belongs to
// ---------------------------------------------------------------------------

struct PoolHandle {
    AiHandle     handle;
    std::string  capability_name;
};

// ---------------------------------------------------------------------------
// CapabilityPool — instance pool for one AI capability
// ---------------------------------------------------------------------------

class CapabilityPool {
public:
    explicit CapabilityPool(std::string cap_name,
                             int min_instances,
                             int max_instances,
                             const std::string& model_dir)
        : cap_name_(std::move(cap_name))
        , max_instances_(max_instances)
        , model_dir_(model_dir)
    {
        // Pre-create min_instances
        for (int i = 0; i < min_instances; ++i) {
            AiHandle h = _create_and_init();
            if (h) idle_.push_back(h);
        }
        total_ = static_cast<int>(idle_.size());
        std::fprintf(stdout, "[InstancePool] %s: pre-created %d instance(s)\n",
                     cap_name_.c_str(), total_);
    }

    ~CapabilityPool() {
        const CapabilityEntry* entry = agilestar_loader_find(cap_name_.c_str());
        if (!entry) return;
        for (AiHandle h : idle_) entry->fn_Destroy(h);
    }

    // Acquire an idle handle, waiting up to timeout_ms milliseconds
    AiHandle acquire(int32_t timeout_ms) {
        std::unique_lock<std::mutex> lk(mutex_);
        auto deadline = std::chrono::steady_clock::now()
                      + std::chrono::milliseconds(timeout_ms > 0 ? timeout_ms : 0);

        while (idle_.empty()) {
            if (total_ < max_instances_) {
                // Create new instance without holding mutex (to avoid blocking)
                lk.unlock();
                AiHandle h = _create_and_init();
                lk.lock();
                if (h) {
                    ++total_;
                    idle_.push_back(h);
                    break;
                }
            }
            if (timeout_ms <= 0) return nullptr;
            if (cv_.wait_until(lk, deadline) == std::cv_status::timeout) {
                return nullptr;
            }
        }

        AiHandle h = idle_.front();
        idle_.pop_front();
        return h;
    }

    void release(AiHandle handle) {
        {
            std::lock_guard<std::mutex> lk(mutex_);
            idle_.push_back(handle);
        }
        cv_.notify_one();
    }

    // Hot-reload: create new instances with new_model_dir, then swap
    int32_t reload(const std::string& new_model_dir) {
        AiHandle new_h = _create_and_init_in(new_model_dir);
        if (!new_h) return AI_ERR_LOAD_FAILED;

        std::lock_guard<std::mutex> lk(mutex_);
        model_dir_ = new_model_dir;

        // Destroy old idle instances
        const CapabilityEntry* entry = agilestar_loader_find(cap_name_.c_str());
        if (entry) {
            for (AiHandle h : idle_) entry->fn_Destroy(h);
        }
        idle_.clear();
        idle_.push_back(new_h);
        total_ = 1;
        return AI_OK;
    }

private:
    AiHandle _create_and_init() {
        return _create_and_init_in(model_dir_);
    }

    AiHandle _create_and_init_in(const std::string& mdir) {
        const CapabilityEntry* entry = agilestar_loader_find(cap_name_.c_str());
        if (!entry) return nullptr;
        AiHandle h = entry->fn_Create(mdir.c_str(), nullptr);
        if (!h) return nullptr;
        int32_t rc = entry->fn_Init(h);
        if (rc != AI_OK) {
            entry->fn_Destroy(h);
            std::fprintf(stderr, "[InstancePool] %s: AiInit failed (rc=%d)\n",
                         cap_name_.c_str(), rc);
            return nullptr;
        }
        return h;
    }

    std::string              cap_name_;
    int                      max_instances_;
    std::string              model_dir_;
    int                      total_ = 0;
    std::deque<AiHandle>     idle_;
    std::mutex               mutex_;
    std::condition_variable  cv_;
};

// ---------------------------------------------------------------------------
// GlobalPool — map of capability_name → CapabilityPool
// ---------------------------------------------------------------------------

class GlobalPool {
public:
    static GlobalPool& instance() {
        static GlobalPool p;
        return p;
    }

    int32_t add_capability(const std::string& cap_name,
                            int min_inst, int max_inst,
                            const std::string& model_dir) {
        std::lock_guard<std::mutex> lk(mutex_);
        pools_[cap_name] = std::make_unique<CapabilityPool>(
            cap_name, min_inst, max_inst, model_dir);
        return AI_OK;
    }

    AiHandle acquire(const char* cap_name, int32_t timeout_ms) {
        std::lock_guard<std::mutex> lk(mutex_);
        auto it = pools_.find(cap_name);
        if (it == pools_.end()) return nullptr;
        return it->second->acquire(timeout_ms);
    }

    void release(AiHandle handle, const char* cap_name) {
        std::lock_guard<std::mutex> lk(mutex_);
        auto it = pools_.find(cap_name);
        if (it != pools_.end()) it->second->release(handle);
    }

    int32_t reload(const char* cap_name, const std::string& new_model_dir) {
        std::lock_guard<std::mutex> lk(mutex_);
        auto it = pools_.find(cap_name);
        if (it == pools_.end()) return AI_ERR_CAPABILITY_MISSING;
        return it->second->reload(new_model_dir);
    }

    void destroy_all() {
        std::lock_guard<std::mutex> lk(mutex_);
        pools_.clear();
    }

private:
    GlobalPool() = default;
    std::mutex mutex_;
    std::unordered_map<std::string, std::unique_ptr<CapabilityPool>> pools_;
};

} // namespace agilestar

// C interface
int agilestar_pool_add(const char* cap_name, int min_inst, int max_inst,
                       const char* model_dir) {
    return agilestar::GlobalPool::instance().add_capability(
        cap_name, min_inst, max_inst, model_dir);
}

AiHandle agilestar_pool_acquire(const char* cap_name, int32_t timeout_ms) {
    return agilestar::GlobalPool::instance().acquire(cap_name, timeout_ms);
}

void agilestar_pool_release(AiHandle handle, const char* cap_name) {
    agilestar::GlobalPool::instance().release(handle, cap_name);
}

int32_t agilestar_pool_reload(const char* cap_name, const char* new_model_dir) {
    return agilestar::GlobalPool::instance().reload(cap_name, new_model_dir);
}

void agilestar_pool_destroy_all() {
    agilestar::GlobalPool::instance().destroy_all();
}
