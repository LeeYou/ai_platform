#ifndef AGILESTAR_AI_RUNTIME_IMPL_H
#define AGILESTAR_AI_RUNTIME_IMPL_H

/**
 * ai_runtime_impl.h
 * Runtime 内部实现头文件（不对外暴露，仅供 runtime/ 目录内部使用）
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "ai_types.h"
#include "ai_capability.h"
#include "ai_runtime.h"

#include <cstdint>
#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// capability_loader.cpp exports (internal linkage helpers)
// ---------------------------------------------------------------------------

namespace agilestar { struct CapabilityEntry; }

int                                  agilestar_loader_init(const char* so_dir);
const agilestar::CapabilityEntry*    agilestar_loader_find(const char* name);
std::vector<std::string>             agilestar_loader_names();
void                                 agilestar_loader_unload_all();

// ---------------------------------------------------------------------------
// instance_pool.cpp exports
// ---------------------------------------------------------------------------

int32_t  agilestar_pool_add(const char* cap_name, int min_inst, int max_inst,
                             const char* model_dir);
AiHandle agilestar_pool_acquire(const char* cap_name, int32_t timeout_ms);
void     agilestar_pool_release(AiHandle handle, const char* cap_name);
int32_t  agilestar_pool_reload(const char* cap_name, const char* new_model_dir);
void     agilestar_pool_destroy_all();

// ---------------------------------------------------------------------------
// license_checker.cpp exports
// ---------------------------------------------------------------------------

void     agilestar_license_set_path(const char* path);
void     agilestar_license_set_pubkey_path(const char* path);
bool     agilestar_license_is_valid(const char* cap_name);
int32_t  agilestar_license_get_json(char* buf, int32_t buf_len);

// ---------------------------------------------------------------------------
// model_loader.cpp exports
// ---------------------------------------------------------------------------

int32_t  agilestar_model_verify(const char* model_dir,
                                 const char* expected_capability);

#endif /* AGILESTAR_AI_RUNTIME_IMPL_H */
