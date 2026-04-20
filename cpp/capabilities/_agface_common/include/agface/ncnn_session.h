#ifndef AGILESTAR_AGFACE_NCNN_SESSION_H
#define AGILESTAR_AGFACE_NCNN_SESSION_H

/**
 * @file ncnn_session.h
 * @brief NCNN 推理会话封装（共享 Net + 每会话 Extractor）。
 *
 * 设计原则：
 *   - ncnn::Net 加载一次，所有池内会话共享同一份权重（节省显存/内存 ∝ pool_size）。
 *   - 每次 forward 创建一次性的 ncnn::Extractor（NCNN 的 Extractor 本身非线程安全；
 *     InstancePool 已保证同一会话不会被多线程并发进入，故无需额外锁）。
 *
 * 移植自旧 ai_agface/src/ai_modules/common/ncnn_session.h。
 */

#include <memory>
#include <string>
#include <vector>

#include <ncnn/net.h>

namespace agface {

class NcnnSession {
public:
    NcnnSession() : m_net(std::make_shared<ncnn::Net>()) {}

    /**
     * 与外部共享 ncnn::Net 构造：推荐方式（与 InstancePool 搭配使用）。
     */
    explicit NcnnSession(std::shared_ptr<ncnn::Net> shared_net)
        : m_net(std::move(shared_net)), m_loaded(m_net != nullptr) {}

    ~NcnnSession()                             = default;
    NcnnSession(const NcnnSession&)            = delete;
    NcnnSession& operator=(const NcnnSession&) = delete;

    /**
     * 自持 Net 时加载模型（param + bin）。
     * 当通过共享 Net 构造时，此方法不应被调用。
     */
    bool load(const std::string& param_path,
              const std::string& bin_path,
              int                num_threads = 1) {
        m_net->opt.lightmode          = true;
        m_net->opt.num_threads        = num_threads;
        m_net->opt.use_vulkan_compute = false;

        if (m_net->load_param(param_path.c_str()) != 0) return false;
        if (m_net->load_model(bin_path.c_str()) != 0) return false;

        m_loaded = true;
        return true;
    }

    /** 创建一个一次性 Extractor（调用方立即使用，不跨线程共享） */
    ncnn::Extractor createExtractor() {
        ncnn::Extractor ex = m_net->create_extractor();
        ex.set_light_mode(true);
        return ex;
    }

    bool                              isLoaded() const { return m_loaded; }
    ncnn::Net&                        net() { return *m_net; }
    const std::shared_ptr<ncnn::Net>& sharedNet() const { return m_net; }

private:
    std::shared_ptr<ncnn::Net> m_net;
    bool                       m_loaded = false;
};

}  // namespace agface

#endif  // AGILESTAR_AGFACE_NCNN_SESSION_H
