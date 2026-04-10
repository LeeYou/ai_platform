"""
Python ctypes bindings for libai_runtime.so

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""
import ctypes
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("prod.ai_runtime_ctypes")

# ---------------------------------------------------------------------------
# C type definitions matching cpp/sdk/ai_types.h
# ---------------------------------------------------------------------------

# typedef void* AiHandle;
AiHandle = ctypes.c_void_p


# typedef struct AiImage
class AiImage(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("width", ctypes.c_int32),
        ("height", ctypes.c_int32),
        ("channels", ctypes.c_int32),
        ("data_type", ctypes.c_int32),    # 0=uint8, 1=float32
        ("color_format", ctypes.c_int32),  # 0=BGR, 1=RGB, 2=GRAY
        ("stride", ctypes.c_int32),
    ]


# typedef struct AiResult
class AiResult(ctypes.Structure):
    _fields_ = [
        ("json_result", ctypes.c_char_p),
        ("result_len", ctypes.c_int32),
        ("error_code", ctypes.c_int32),
        ("error_msg", ctypes.c_char_p),
    ]


# AiErrorCode enum
AI_OK = 0
AI_ERR_INVALID_PARAM = 1001
AI_ERR_IMAGE_DECODE = 1002
AI_ERR_CAPABILITY_MISSING = 2001
AI_ERR_LOAD_FAILED = 2002
AI_ERR_MODEL_CORRUPT = 2003
AI_ERR_INFER_FAILED = 2004
AI_ERR_LICENSE_INVALID = 4001
AI_ERR_LICENSE_EXPIRED = 4002
AI_ERR_LICENSE_NOT_YET_VALID = 4003
AI_ERR_CAP_NOT_LICENSED = 4004
AI_ERR_LICENSE_MISMATCH = 4005
AI_ERR_LICENSE_SIGNATURE_INVALID = 4006
AI_ERR_INTERNAL = 5001


# ---------------------------------------------------------------------------
# Runtime singleton wrapper
# ---------------------------------------------------------------------------

class AiRuntime:
    """Wrapper for libai_runtime.so C API"""

    def __init__(self, so_path: str):
        self._lib = ctypes.CDLL(so_path)
        self._initialized = False

        # Define function signatures
        # int32_t AiRuntimeInit(const char* so_dir, const char* model_base_dir, const char* license_path)
        self._lib.AiRuntimeInit.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        self._lib.AiRuntimeInit.restype = ctypes.c_int32

        # int32_t AiRuntimeGetCapabilities(char* buf, int32_t buf_len)
        self._lib.AiRuntimeGetCapabilities.argtypes = [ctypes.c_char_p, ctypes.c_int32]
        self._lib.AiRuntimeGetCapabilities.restype = ctypes.c_int32

        # AiHandle AiRuntimeAcquire(const char* capability_name, int32_t timeout_ms)
        self._lib.AiRuntimeAcquire.argtypes = [ctypes.c_char_p, ctypes.c_int32]
        self._lib.AiRuntimeAcquire.restype = AiHandle

        # void AiRuntimeRelease(AiHandle handle)
        self._lib.AiRuntimeRelease.argtypes = [AiHandle]
        self._lib.AiRuntimeRelease.restype = None

        # int32_t AiRuntimeReload(const char* capability_name)
        self._lib.AiRuntimeReload.argtypes = [ctypes.c_char_p]
        self._lib.AiRuntimeReload.restype = ctypes.c_int32

        # int32_t AiRuntimeGetLicenseStatus(char* buf, int32_t buf_len)
        self._lib.AiRuntimeGetLicenseStatus.argtypes = [ctypes.c_char_p, ctypes.c_int32]
        self._lib.AiRuntimeGetLicenseStatus.restype = ctypes.c_int32

        # int32_t AiRuntimeGetLastError(char* buf, int32_t buf_len)
        self._lib.AiRuntimeGetLastError.argtypes = [ctypes.c_char_p, ctypes.c_int32]
        self._lib.AiRuntimeGetLastError.restype = ctypes.c_int32

        # void AiRuntimeDestroy(void)
        self._lib.AiRuntimeDestroy.argtypes = []
        self._lib.AiRuntimeDestroy.restype = None

        # int32_t AiRuntimeInfer(AiHandle handle, const AiImage* input, AiResult* output)
        self._lib.AiRuntimeInfer.argtypes = [AiHandle, ctypes.POINTER(AiImage), ctypes.POINTER(AiResult)]
        self._lib.AiRuntimeInfer.restype = ctypes.c_int32

        # void AiRuntimeFreeResult(AiResult* result)
        self._lib.AiRuntimeFreeResult.argtypes = [ctypes.POINTER(AiResult)]
        self._lib.AiRuntimeFreeResult.restype = None

        logger.info("Loaded libai_runtime.so from %s", so_path)

    def init(self, so_dir: str, model_base_dir: str, license_path: str) -> int:
        """Initialize Runtime layer with SO directory, model directory, and license."""
        ret = self._lib.AiRuntimeInit(
            so_dir.encode("utf-8"),
            model_base_dir.encode("utf-8"),
            license_path.encode("utf-8"),
        )
        if ret == AI_OK:
            self._initialized = True
            logger.info("AiRuntimeInit successful")
        else:
            logger.error("AiRuntimeInit failed with error code %d", ret)
        return ret

    def get_capabilities(self) -> list[dict[str, Any]]:
        """Get list of loaded capabilities as JSON."""
        if not self._initialized:
            logger.warning("Runtime not initialized, returning empty capabilities")
            return []

        # First call to get required buffer size
        buf_size = self._lib.AiRuntimeGetCapabilities(None, 0)
        if buf_size <= 0:
            logger.warning("No capabilities loaded or error getting size")
            return []

        # Allocate buffer and get actual data
        buf = ctypes.create_string_buffer(buf_size + 1)
        ret = self._lib.AiRuntimeGetCapabilities(buf, buf_size + 1)
        if ret < 0:
            logger.error("Failed to get capabilities, error code: %d", ret)
            return []

        try:
            caps_json = buf.value.decode("utf-8")
            data = json.loads(caps_json)
            return data.get("capabilities", [])
        except Exception as e:
            logger.error("Failed to parse capabilities JSON: %s", e)
            return []

    def acquire(self, capability_name: str, timeout_ms: int = 30000) -> Optional[AiHandle]:
        """Acquire an inference instance from the capability pool."""
        if not self._initialized:
            logger.error("Runtime not initialized")
            return None

        handle = self._lib.AiRuntimeAcquire(capability_name.encode("utf-8"), timeout_ms)
        if not handle:
            logger.warning("Failed to acquire instance for %s (timeout or not found)", capability_name)
        return handle

    def release(self, handle: AiHandle) -> None:
        """Release an inference instance back to the pool."""
        if handle:
            self._lib.AiRuntimeRelease(handle)

    def reload(self, capability_name: str) -> int:
        """Trigger hot reload for a specific capability."""
        ret = self._lib.AiRuntimeReload(capability_name.encode("utf-8"))
        if ret == AI_OK:
            logger.info("Reload triggered for %s", capability_name)
        else:
            logger.error("Reload failed for %s, error code: %d", capability_name, ret)
        return ret

    def get_license_status(self) -> Optional[dict[str, Any]]:
        """Get current license status as JSON."""
        if not self._initialized:
            logger.warning("Runtime not initialized, cannot get license status")
            return None

        # First call to get required buffer size
        buf_size = self._lib.AiRuntimeGetLicenseStatus(None, 0)
        if buf_size <= 0:
            logger.warning("Failed to get license status buffer size")
            return None

        # Allocate buffer and get actual data
        buf = ctypes.create_string_buffer(buf_size + 1)
        ret = self._lib.AiRuntimeGetLicenseStatus(buf, buf_size + 1)
        if ret < 0:
            logger.error("Failed to get license status, error code: %d", ret)
            return None

        try:
            license_json = buf.value.decode("utf-8")
            return json.loads(license_json)
        except Exception as e:
            logger.error("Failed to parse license status JSON: %s", e)
            return None

    def get_last_error(self) -> Optional[dict[str, Any]]:
        """Get the last acquire failure detail for the current thread."""
        if not self._initialized:
            return None

        buf_size = self._lib.AiRuntimeGetLastError(None, 0)
        if buf_size <= 0:
            return None

        buf = ctypes.create_string_buffer(buf_size + 1)
        ret = self._lib.AiRuntimeGetLastError(buf, buf_size + 1)
        if ret <= 0:
            return None

        try:
            return json.loads(buf.value.decode("utf-8"))
        except Exception as e:
            logger.error("Failed to parse runtime last error JSON: %s", e)
            return None

    def infer(self, handle: AiHandle, image_data: bytes, width: int, height: int, channels: int = 3) -> dict[str, Any]:
        """Run inference using acquired instance handle (proper instance pool usage).

        This method should be used instead of directly creating AiCapability instances,
        as it leverages the Runtime's instance pool for better performance.

        Args:
            handle: Instance handle from acquire()
            image_data: Raw image bytes (BGR format)
            width: Image width
            height: Image height
            channels: Image channels (default 3 for BGR)

        Returns:
            dict with "error_code" and optionally "result" or "error_msg"
        """
        if not handle:
            return {"error_code": AI_ERR_INVALID_PARAM, "error_msg": "Handle is NULL"}

        # Create AiImage structure
        img_array = (ctypes.c_uint8 * len(image_data)).from_buffer_copy(image_data)
        ai_img = AiImage(
            data=ctypes.cast(img_array, ctypes.POINTER(ctypes.c_uint8)),
            width=width,
            height=height,
            channels=channels,
            data_type=0,  # uint8
            color_format=0,  # BGR
            stride=0,  # tightly packed
        )

        # Create AiResult structure
        ai_result = AiResult()

        # Call AiRuntimeInfer (uses instance pool)
        ret = self._lib.AiRuntimeInfer(handle, ctypes.byref(ai_img), ctypes.byref(ai_result))

        # Parse result
        result = {
            "error_code": ai_result.error_code,
        }

        if ai_result.json_result:
            try:
                result["result"] = json.loads(ai_result.json_result.decode("utf-8"))
            except Exception as e:
                logger.error("Failed to parse result JSON: %s", e)
                result["result"] = {}

        if ai_result.error_msg:
            result["error_msg"] = ai_result.error_msg.decode("utf-8")

        # Free result memory allocated by SO
        self._lib.AiRuntimeFreeResult(ctypes.byref(ai_result))

        return result

    def destroy(self) -> None:
        """Destroy runtime and cleanup all resources."""
        if self._initialized:
            self._lib.AiRuntimeDestroy()
            self._initialized = False
            logger.info("Runtime destroyed")


# ---------------------------------------------------------------------------
# Capability plugin C API (for direct inference if needed)
# ---------------------------------------------------------------------------

class AiCapability:
    """Wrapper for individual capability SO (lib<capability>.so)"""

    def __init__(self, so_path: str):
        self._lib = ctypes.CDLL(so_path)
        self._handle: Optional[AiHandle] = None

        # int32_t AiGetAbiVersion(void)
        self._lib.AiGetAbiVersion.argtypes = []
        self._lib.AiGetAbiVersion.restype = ctypes.c_int32

        # AiHandle AiCreate(const char* model_dir, const char* config_json)
        self._lib.AiCreate.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._lib.AiCreate.restype = AiHandle

        # int32_t AiInit(AiHandle handle)
        self._lib.AiInit.argtypes = [AiHandle]
        self._lib.AiInit.restype = ctypes.c_int32

        # int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output)
        self._lib.AiInfer.argtypes = [AiHandle, ctypes.POINTER(AiImage), ctypes.POINTER(AiResult)]
        self._lib.AiInfer.restype = ctypes.c_int32

        # void AiFreeResult(AiResult* result)
        self._lib.AiFreeResult.argtypes = [ctypes.POINTER(AiResult)]
        self._lib.AiFreeResult.restype = None

        # void AiDestroy(AiHandle handle)
        self._lib.AiDestroy.argtypes = [AiHandle]
        self._lib.AiDestroy.restype = None

        logger.info("Loaded capability SO from %s", so_path)

    def get_abi_version(self) -> int:
        """Get ABI version of the capability SO."""
        return self._lib.AiGetAbiVersion()

    def create(self, model_dir: str, config_json: str = "{}") -> bool:
        """Create capability instance."""
        self._handle = self._lib.AiCreate(
            model_dir.encode("utf-8"),
            config_json.encode("utf-8"),
        )
        return self._handle is not None

    def init(self) -> int:
        """Initialize capability instance."""
        if not self._handle:
            logger.error("Cannot init: handle is NULL")
            return AI_ERR_INVALID_PARAM
        return self._lib.AiInit(self._handle)

    def infer(self, image_data: bytes, width: int, height: int, channels: int = 3) -> dict[str, Any]:
        """Run inference on image data."""
        if not self._handle:
            return {"error_code": AI_ERR_INVALID_PARAM, "error_msg": "Handle is NULL"}

        # Create AiImage structure
        img_array = (ctypes.c_uint8 * len(image_data)).from_buffer_copy(image_data)
        ai_img = AiImage(
            data=ctypes.cast(img_array, ctypes.POINTER(ctypes.c_uint8)),
            width=width,
            height=height,
            channels=channels,
            data_type=0,  # uint8
            color_format=0,  # BGR
            stride=0,  # tightly packed
        )

        # Create AiResult structure
        ai_result = AiResult()

        # Call AiInfer
        ret = self._lib.AiInfer(self._handle, ctypes.byref(ai_img), ctypes.byref(ai_result))

        # Parse result
        result = {
            "error_code": ai_result.error_code,
        }

        if ai_result.json_result:
            try:
                result["result"] = json.loads(ai_result.json_result.decode("utf-8"))
            except Exception as e:
                logger.error("Failed to parse result JSON: %s", e)
                result["result"] = {}

        if ai_result.error_msg:
            result["error_msg"] = ai_result.error_msg.decode("utf-8")

        # Free result memory allocated by SO
        self._lib.AiRuntimeFreeResult(ctypes.byref(ai_result))

        return result

    def destroy(self) -> None:
        """Destroy capability instance."""
        if self._handle:
            self._lib.AiDestroy(self._handle)
            self._handle = None


# ---------------------------------------------------------------------------
# Global runtime instance
# ---------------------------------------------------------------------------

_runtime_instance: Optional[AiRuntime] = None


def get_runtime() -> Optional[AiRuntime]:
    """Get global runtime instance (must call init_runtime first)."""
    return _runtime_instance


def init_runtime(so_path: str, so_dir: str, model_base_dir: str, license_path: str) -> bool:
    """Initialize global runtime instance."""
    global _runtime_instance

    if _runtime_instance is not None:
        logger.warning("Runtime already initialized")
        return True

    try:
        _runtime_instance = AiRuntime(so_path)
        ret = _runtime_instance.init(so_dir, model_base_dir, license_path)
        if ret != AI_OK:
            logger.error("Runtime initialization failed with code %d", ret)
            _runtime_instance = None
            return False
        return True
    except Exception as e:
        logger.error("Failed to initialize runtime: %s", e, exc_info=True)
        _runtime_instance = None
        return False


def destroy_runtime() -> None:
    """Destroy global runtime instance."""
    global _runtime_instance
    if _runtime_instance:
        _runtime_instance.destroy()
        _runtime_instance = None
