# Production Web Service

**北京爱知之星科技股份有限公司 (Agile Star)**

## Architecture

This service implements **Layer 1 (HTTP Service)** of the production container architecture.

### Correct Architecture (5-Layer Production Container)

```
Layer 0: Web Management (Vue3 frontend)
Layer 1: HTTP Service (Python FastAPI) ← THIS SERVICE
Layer 2: Runtime Layer (Python ctypes → libai_runtime.so)
Layer 3: Capability Plugins (C++ SO files: lib<capability>.so)
Layer 4: Model Packages (ONNX files)
```

### Key Principles

1. **NO Python ONNXRuntime inference** - Production uses ONLY C++ SO libraries
2. **GPU-first, CPU fallback** - Prefer GPU when available, fallback to CPU
3. **Mount > Built-in priority** - External resources override container defaults

## Current Status

⚠️ **IMPORTANT**: This service requires compiled C++ SO files to function.

### Required C++ Libraries (NOT YET COMPILED)

The following libraries must be compiled using the **ai-builder** service before this production service can run inference:

1. **`libai_runtime.so`** - Runtime layer that manages capability loading, instance pools, and license checking
   - Source: `cpp/runtime/`
   - Must be placed in: `/app/libs/` or `/mnt/ai_platform/libs/`

2. **`lib<capability>.so`** - Individual capability plugins (e.g., `libface_detect.so`)
   - Source: `cpp/capabilities/<capability>/`
   - Must be placed in: `/app/libs/` or `/mnt/ai_platform/libs/`

### Build Instructions

See `docs/design/build_service.md` for detailed instructions on:

1. Setting up the ai-builder Docker containers
2. Compiling libai_runtime.so and capability SO files
3. Multi-platform compilation (Linux x86_64, ARM, Windows)
4. GPU vs CPU builds

### Workflow

```
Train (Python)
  → Export models
  → Test (Python)
  → Compile SO (ai-builder)
  → Deploy to Production (THIS SERVICE)
```

## Files Modified

### Correct Implementation (C++ SO via ctypes)

- **`ai_runtime_ctypes.py`** ✅ - Python ctypes bindings for libai_runtime.so
- **`main.py`** ✅ - Updated to use ctypes Runtime API instead of Python ONNXRuntime
- **`resource_resolver.py`** ✅ - Added functions to resolve SO paths
- **`requirements.txt`** ✅ - Removed onnxruntime-gpu (not needed)

### Incorrect Implementation (REMOVED)

- **Python ONNXRuntime production path** ❌ - Fully removed; production only allows `main.py` → `ai_runtime_ctypes.py` → `libai_runtime.so`

## Running the Service

### Without C++ SO Files (Development Mode)

The service will start but cannot perform inference:

```bash
python main.py
# ERROR: libai_runtime.so not found — cannot start
```

### With C++ SO Files (Production Mode)

1. Compile libai_runtime.so and capability SO files using ai-builder
2. Place compiled SO files in `/app/libs/` or mount via Docker volume
3. Place trained models in `/app/models/` or mount via Docker volume
4. Start the service:

```bash
python main.py
# SUCCESS: Runtime loaded 3 capabilities: ['face_detect', 'handwriting_reco', ...]
```

## API Endpoints

- `GET /api/v1/health` - Health check with capabilities and license status
- `GET /api/v1/capabilities` - List all loaded capabilities
- `POST /api/v1/infer/{capability}` - Run inference (requires C++ SO)
- `POST /api/v1/admin/reload` - Hot reload all capabilities
- `POST /api/v1/admin/reload/{capability}` - Hot reload specific capability
- `GET /api/v1/license/status` - License status
- `GET /docs` - Swagger API documentation

## Performance

Expected inference performance (C++ SO vs Python ORT):

- **Python ONNXRuntime**: ~450-900ms per inference (SLOW - NOT USED)
- **C++ SO (CPU)**: ~50-150ms per inference
- **C++ SO (GPU)**: ~10-50ms per inference

The 10x performance improvement is why we use C++ SO in production.

## License Validation

License validation happens at two levels:

1. **HTTP Layer (Python)** - Fast cache-based validation (60s TTL)
2. **Runtime Layer (C++)** - Cryptographic signature verification

See `docs/design/architecture.md` for details.

---

*Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn*
