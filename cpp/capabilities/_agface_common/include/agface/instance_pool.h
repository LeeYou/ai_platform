#ifndef AGILESTAR_AGFACE_INSTANCE_POOL_H
#define AGILESTAR_AGFACE_INSTANCE_POOL_H

/**
 * @file instance_pool.h
 * @brief Thread-safe object instance pool with RAII borrowing.
 *
 * 移植自旧 ai_agface/src/infra/instance_pool.h，剥离了对 LicenseChecker 的耦合。
 * License 校验由 libai_runtime.so 在 Runtime 层统一处理，能力插件不再内置校验。
 *
 * 线程安全：所有 public 方法均为完全线程安全。
 */

#include <cassert>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <queue>
#include <vector>

namespace agface {

/**
 * 固定大小的对象实例池 + RAII 借出。
 * 每个 agface_* 能力插件一个实例池（对应一种 NCNN 模型的推理会话）。
 */
template <typename T>
class InstancePool {
public:
    class ScopedInstance {
    public:
        ScopedInstance() : m_pool(nullptr), m_ptr(nullptr) {}
        ScopedInstance(InstancePool* pool, T* ptr) : m_pool(pool), m_ptr(ptr) {}

        ~ScopedInstance() {
            if (m_pool && m_ptr) m_pool->release(m_ptr);
        }

        ScopedInstance(ScopedInstance&& other) noexcept
            : m_pool(other.m_pool), m_ptr(other.m_ptr) {
            other.m_pool = nullptr;
            other.m_ptr  = nullptr;
        }
        ScopedInstance& operator=(ScopedInstance&& other) noexcept {
            if (this != &other) {
                if (m_pool && m_ptr) m_pool->release(m_ptr);
                m_pool       = other.m_pool;
                m_ptr        = other.m_ptr;
                other.m_pool = nullptr;
                other.m_ptr  = nullptr;
            }
            return *this;
        }
        ScopedInstance(const ScopedInstance&)            = delete;
        ScopedInstance& operator=(const ScopedInstance&) = delete;

        T*   get() const { return m_ptr; }
        T*   operator->() const { return m_ptr; }
        T&   operator*() const { return *m_ptr; }
        explicit operator bool() const { return m_ptr != nullptr; }

    private:
        InstancePool* m_pool;
        T*            m_ptr;
    };

    InstancePool(int pool_size, std::function<std::unique_ptr<T>()> factory)
        : m_total(pool_size) {
        assert(pool_size > 0);
        m_instances.reserve(pool_size);
        for (int i = 0; i < pool_size; ++i) {
            auto inst = factory();
            if (!inst) continue;  // 允许工厂返回 nullptr，池会变小但不崩
            m_free_queue.push(inst.get());
            m_instances.push_back(std::move(inst));
        }
        m_total = static_cast<int>(m_instances.size());
    }

    ~InstancePool() = default;
    InstancePool(const InstancePool&)            = delete;
    InstancePool& operator=(const InstancePool&) = delete;

    /**
     * 从池中借出一个实例。
     * @param timeout_ms  -1=无限等待，0=非阻塞，>0=毫秒超时
     */
    ScopedInstance acquire(int timeout_ms = 5000) {
        std::unique_lock<std::mutex> lock(m_mutex);
        if (timeout_ms == 0) {
            if (m_free_queue.empty()) return ScopedInstance();
        } else if (timeout_ms < 0) {
            m_cv.wait(lock, [this]() { return !m_free_queue.empty(); });
        } else {
            bool ok = m_cv.wait_for(lock,
                                    std::chrono::milliseconds(timeout_ms),
                                    [this]() { return !m_free_queue.empty(); });
            if (!ok) return ScopedInstance();
        }
        T* ptr = m_free_queue.front();
        m_free_queue.pop();
        return ScopedInstance(this, ptr);
    }

    int available() const {
        std::lock_guard<std::mutex> lock(m_mutex);
        return static_cast<int>(m_free_queue.size());
    }
    int total() const { return m_total; }

private:
    void release(T* ptr) {
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            m_free_queue.push(ptr);
        }
        m_cv.notify_one();
    }

    int                              m_total;
    std::vector<std::unique_ptr<T>>  m_instances;
    std::queue<T*>                   m_free_queue;
    mutable std::mutex               m_mutex;
    std::condition_variable          m_cv;
};

}  // namespace agface

#endif  // AGILESTAR_AGFACE_INSTANCE_POOL_H
