#include "agface/manifest.h"

#include <cstdio>
#include <fstream>
#include <sstream>

#include <nlohmann/json.hpp>

namespace agface {

using nlohmann::json;

static std::string joinPath(const std::string& dir, const std::string& name) {
    if (dir.empty()) return name;
    char last = dir.back();
    if (last == '/' || last == '\\') return dir + name;
#ifdef _WIN32
    return dir + "\\" + name;
#else
    return dir + "/" + name;
#endif
}

static bool readEntireFile(const std::string& path, std::string* out) {
    std::ifstream f(path, std::ios::in | std::ios::binary);
    if (!f.is_open()) return false;
    std::ostringstream ss;
    ss << f.rdbuf();
    *out = ss.str();
    return true;
}

bool loadManifestFromDir(const std::string& model_dir,
                         NcnnManifest*      out,
                         std::string*       error_out) {
    auto fail = [&](const std::string& msg) {
        if (error_out) *error_out = msg;
        return false;
    };
    if (!out) return fail("out pointer is null");
    if (model_dir.empty()) return fail("model_dir is empty");

    const std::string manifest_path = joinPath(model_dir, "manifest.json");
    std::string       text;
    if (!readEntireFile(manifest_path, &text)) {
        return fail("failed to read manifest.json at: " + manifest_path);
    }

    json j;
    try {
        j = json::parse(text);
    } catch (const std::exception& e) {
        return fail(std::string("manifest.json parse error: ") + e.what());
    }

    try {
        out->name    = j.value("name", "");
        out->version = j.value("version", "");
        out->backend = j.value("backend", "ncnn");

        out->param_file = j.value("param_file", "");
        out->bin_file   = j.value("bin_file", "");
        if (out->param_file.empty() || out->bin_file.empty()) {
            return fail("manifest.json must specify 'param_file' and 'bin_file'");
        }

        if (j.contains("input") && j["input"].is_object()) {
            const auto& in      = j["input"];
            out->input_blob     = in.value("blob", out->input_blob);
            out->input_base_size = in.value("base_size", out->input_base_size);
            out->input_color    = in.value("color", out->input_color);
            if (in.contains("mean") && in["mean"].is_array() && in["mean"].size() == 3) {
                for (int i = 0; i < 3; ++i) out->mean[i] = in["mean"][i].get<float>();
            }
            if (in.contains("norm") && in["norm"].is_array() && in["norm"].size() == 3) {
                for (int i = 0; i < 3; ++i) out->norm[i] = in["norm"][i].get<float>();
            }
        }
        if (j.contains("output") && j["output"].is_object()) {
            const auto& ot     = j["output"];
            out->output_blob   = ot.value("blob", out->output_blob);
            out->output_format = ot.value("format", out->output_format);
        }
        if (j.contains("thresholds") && j["thresholds"].is_object()) {
            const auto& th       = j["thresholds"];
            out->score_threshold = th.value("score", out->score_threshold);
            out->min_face        = th.value("min_face", out->min_face);
            out->max_image_dim   = th.value("max_image_dim", out->max_image_dim);
        }
    } catch (const std::exception& e) {
        return fail(std::string("manifest.json field extraction failed: ") + e.what());
    }

    out->param_path = joinPath(model_dir, out->param_file);
    out->bin_path   = joinPath(model_dir, out->bin_file);

    // 基础存在性检查
    std::ifstream p(out->param_path);
    if (!p.is_open()) return fail("param file not found: " + out->param_path);
    std::ifstream b(out->bin_path, std::ios::binary);
    if (!b.is_open()) return fail("bin file not found: " + out->bin_path);

    return true;
}

}  // namespace agface
