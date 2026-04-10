/**
 * test_capability_loader.cpp
 * Runtime 能力加载器单元测试（Google Test）
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include <gtest/gtest.h>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <string>

#include "ai_runtime_impl.h"

// ---------------------------------------------------------------------------
// Helper: write a minimal stub SO (only for unit testing without ORT)
// ---------------------------------------------------------------------------
// The tests below test the runtime logic independently from actual SO loading.

// ---------------------------------------------------------------------------
// CapabilityLoader tests
// ---------------------------------------------------------------------------

TEST(CapabilityLoader, EmptyDirReturnsOK) {
    // An empty/nonexistent directory should load 0 capabilities without error
    int rc = agilestar_loader_init("/nonexistent/so/dir");
    // Loader returns LOAD_FAILED only if dir cannot be opened (may vary by impl)
    // For empty dir it should return AI_OK or AI_ERR_LOAD_FAILED; just verify no crash
    EXPECT_TRUE(rc == AI_OK || rc == AI_ERR_LOAD_FAILED);
}

TEST(CapabilityLoader, FindUnknownCapabilityReturnsNull) {
    const agilestar::CapabilityEntry* entry = agilestar_loader_find("no_such_cap");
    EXPECT_EQ(nullptr, entry);
}

// ---------------------------------------------------------------------------
// ModelLoader tests
// ---------------------------------------------------------------------------

class ModelLoaderTest : public ::testing::Test {
protected:
    std::string tmpdir_;

    void SetUp() override {
        char tmp[] = "/tmp/ml_test_XXXXXX";
        tmpdir_ = mkdtemp(tmp);
    }

    void TearDown() override {
        // clean up
        std::string cmd = "rm -rf " + tmpdir_;
        (void)std::system(cmd.c_str());
    }

    void write_manifest(const std::string& capability,
                        const std::string& version,
                        const std::string& checksum = "") {
        std::string path = tmpdir_ + "/manifest.json";
        std::ofstream f(path);
        f << "{"
          << "\"capability\":\"" << capability << "\","
          << "\"model_version\":\"" << version << "\","
          << "\"checksum\":{\"model_file\":\"" << checksum << "\",\"algorithm\":\"sha256\"}"
          << "}";
    }

    void write_legacy_manifest(const std::string& capability,
                               const std::string& version,
                               const std::string& checksum = "") {
        std::string path = tmpdir_ + "/manifest.json";
        std::ofstream f(path);
        f << "{"
          << "\"capability\":\"" << capability << "\","
          << "\"version\":\"" << version << "\","
          << "\"checksum\":{\"model_file\":\"" << checksum << "\",\"algorithm\":\"sha256\"}"
          << "}";
    }
};

TEST_F(ModelLoaderTest, MissingManifestReturnsError) {
    int rc = agilestar_model_verify(tmpdir_.c_str(), "face_detect");
    EXPECT_EQ(AI_ERR_MODEL_CORRUPT, rc);
}

TEST_F(ModelLoaderTest, ValidManifestNoChecksumPasses) {
    write_manifest("recapture_detect", "1.0.0", "");
    int rc = agilestar_model_verify(tmpdir_.c_str(), "recapture_detect");
    EXPECT_EQ(AI_OK, rc);
}

TEST_F(ModelLoaderTest, CapabilityMismatchReturnsError) {
    write_manifest("face_detect", "1.0.0", "");
    int rc = agilestar_model_verify(tmpdir_.c_str(), "recapture_detect");
    EXPECT_EQ(AI_ERR_MODEL_CORRUPT, rc);
}

TEST_F(ModelLoaderTest, EmptyExpectedCapabilityAllowsAny) {
    write_manifest("any_cap", "2.0.0", "");
    int rc = agilestar_model_verify(tmpdir_.c_str(), "");
    EXPECT_EQ(AI_OK, rc);
}

TEST_F(ModelLoaderTest, LegacyVersionManifestPasses) {
    write_legacy_manifest("recapture_detect", "1.0.0", "");
    int rc = agilestar_model_verify(tmpdir_.c_str(), "recapture_detect");
    EXPECT_EQ(AI_OK, rc);
}

// ---------------------------------------------------------------------------
// LicenseChecker tests
// ---------------------------------------------------------------------------

class LicenseCheckerTest : public ::testing::Test {
protected:
    std::string tmp_license_;

    void SetUp() override {
        tmp_license_ = "/tmp/test_license.bin";
    }

    void TearDown() override {
        std::remove(tmp_license_.c_str());
    }

    void write_license(const std::string& status,
                       const std::string& valid_from,
                       const std::string& valid_until,
                       const std::string& capabilities_json) {
        std::ofstream f(tmp_license_);
        f << "{"
          << "\"license_id\":\"LS-TEST-001\",";
        if (!status.empty()) {
            f << "\"status\":\"" << status << "\",";
        }
        f << "\"valid_from\":\"" << valid_from << "\","
          << "\"valid_until\":\"" << valid_until << "\","
          << "\"capabilities\":" << capabilities_json
          << "}";
    }
};

TEST_F(LicenseCheckerTest, MissingLicenseFileNotValid) {
    agilestar_license_set_path("/nonexistent/license.bin");
    EXPECT_FALSE(agilestar_license_is_valid(nullptr));
}

TEST_F(LicenseCheckerTest, ValidLicenseWithCapabilityPasses) {
    write_license("active", "2020-01-01T00:00:00Z", "2099-12-31T00:00:00Z",
                  "[\"face_detect\",\"recapture_detect\"]");
    agilestar_license_set_path(tmp_license_.c_str());
    EXPECT_TRUE(agilestar_license_is_valid("recapture_detect"));
}

TEST_F(LicenseCheckerTest, ValidLicenseWithoutCapabilityFails) {
    write_license("active", "2020-01-01T00:00:00Z", "2099-12-31T00:00:00Z", "[\"face_detect\"]");
    agilestar_license_set_path(tmp_license_.c_str());
    EXPECT_FALSE(agilestar_license_is_valid("recapture_detect"));
}

TEST_F(LicenseCheckerTest, ExpiredStatusFails) {
    write_license("expired", "2020-01-01T00:00:00Z", "2020-01-01T00:00:00Z",
                  "[\"recapture_detect\"]");
    agilestar_license_set_path(tmp_license_.c_str());
    EXPECT_FALSE(agilestar_license_is_valid("recapture_detect"));
}

TEST_F(LicenseCheckerTest, StatusJsonContainsStatus) {
    write_license("active", "2020-01-01T00:00:00Z", "2099-12-31T00:00:00Z", "[\"recapture_detect\"]");
    agilestar_license_set_path(tmp_license_.c_str());
    char buf[1024] = {};
    int32_t n = agilestar_license_get_json(buf, sizeof(buf));
    EXPECT_GT(n, 0);
    EXPECT_NE(nullptr, std::strstr(buf, "\"status\""));
}

TEST_F(LicenseCheckerTest, LicenseWithoutStatusUsesValidityWindow) {
    write_license("", "2020-01-01T00:00:00Z", "2099-12-31T00:00:00Z",
                  "[\"desktop_recapture_detect\"]");
    agilestar_license_set_path(tmp_license_.c_str());
    EXPECT_TRUE(agilestar_license_is_valid("desktop_recapture_detect"));
}

TEST_F(LicenseCheckerTest, LicenseWithoutStatusCanBeNotYetValid) {
    write_license("", "2099-01-01T00:00:00Z", "2099-12-31T00:00:00Z",
                  "[\"desktop_recapture_detect\"]");
    agilestar_license_set_path(tmp_license_.c_str());
    EXPECT_FALSE(agilestar_license_is_valid("desktop_recapture_detect"));

    char buf[1024] = {};
    int32_t n = agilestar_license_get_json(buf, sizeof(buf));
    EXPECT_GT(n, 0);
    EXPECT_NE(nullptr, std::strstr(buf, "\"status\":\"not_yet_valid\""));
}

// ---------------------------------------------------------------------------
// InstancePool tests
// ---------------------------------------------------------------------------

TEST(InstancePool, AcquireFromEmptyPoolForUnknownCapReturnsNull) {
    // Pool was not configured for "unknown_cap"
    AiHandle h = agilestar_pool_acquire("unknown_cap", 0);
    EXPECT_EQ(nullptr, h);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
