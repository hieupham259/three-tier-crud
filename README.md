# three-tier-crud

Ứng dụng CRUD ba tầng, production-oriented, cho homelab Kubernetes:

```text
browser ──> Ingress ──> frontend Service :80 ──> Nginx unprivileged :8080 (static SPA)
                                                   └── /api/ ──> backend Service :8000 ──> FastAPI (PyMongo Async)
                                                                                              └── mongodb:27017
```

- Contract dữ liệu và API: `runbook-k8s-vmware-phase2.md` §4.2.
- Manifest Kubernetes: **không** nằm trong repo này. Operator chép nguyên văn từ §8–§11 của runbook vào
  `k8s/` và chỉ thay placeholder image/domain.

## 1. Cấu trúc

```text
three-tier-crud/
├── frontend/            React + Vite + TypeScript, build ra static, chạy bằng nginx-unprivileged :8080
│   ├── Dockerfile       multi-stage: deps → build (typecheck + test + build) → nginx runtime
│   ├── nginx.conf       SPA fallback, GET /healthz, reverse proxy /api/ → http://backend:8000/api/
│   ├── package.json     version ghim chính xác (không caret)
│   ├── package-lock.json
│   └── src/             api/client.ts (relative /api), App.tsx, components/, *.test.ts(x)
├── backend/             FastAPI + AsyncMongoClient, listen 0.0.0.0:8000, uid 10001
│   ├── Dockerfile       multi-stage: deps → test (pytest) → runtime
│   ├── requirements.txt         closure runtime, pin đầy đủ
│   ├── requirements-dev.txt     closure test, pin đầy đủ
│   ├── pyproject.toml           metadata + cấu hình pytest
│   ├── app/             config.py, db.py, models.py, redaction.py, routers/{health,items}.py, main.py
│   └── tests/           fakes.py (double cho PyMongo Async) + test_*.py
├── k8s/.gitkeep         thư mục rỗng có chủ đích
└── README.md
```

## 2. Phiên bản đã chốt

Chốt ngày 06/09/2026 theo metadata npm registry, PyPI và Docker Hub. Mọi lần build lại phải dùng
đúng lockfile đã commit; đổi version phải cập nhật bảng này cùng lúc.

| Thành phần | Version | Ghi chú |
| --- | --- | --- |
| React / react-dom | 19.2.8 | |
| Vite | 8.2.2 | |
| @vitejs/plugin-react | 6.1.1 | yêu cầu Vite 8 |
| TypeScript | 6.0.3 | dòng 6.0 mà template `create-vite` hiện dùng |
| Vitest | 4.1.11 | dòng 4.x, hỗ trợ Vite 8 và Node 20/22/24 |
| jsdom | 29.1.1 | |
| @testing-library/react / dom / user-event / jest-dom | 16.3.3 / 10.4.1 / 14.6.7 / 7.0.1 | |
| @types/node / @types/react / @types/react-dom | 24.13.3 / 19.2.18 / 19.2.7 | |
| **Base image build frontend** | `node:24.20.0-alpine3.24` | Node 24 LTS |
| **Base image runtime frontend** | `nginxinc/nginx-unprivileged:1.30.4-alpine3.24` | nhánh stable 1.30 |
| FastAPI | 0.141.1 | |
| Starlette | 1.6.0 | transitive của FastAPI |
| Pydantic / pydantic-core | 2.13.5 / 2.46.5 | |
| PyMongo | 4.18.0 | official Async API, không dùng Motor |
| uvicorn | 0.52.4 | không dùng extra `standard` |
| pytest / httpx | 9.1.1 / 0.28.1 | chỉ trong stage test |
| **Base image build, test và runtime backend** | `python:3.13.15-slim-trixie` | cùng một tag cho ba stage |

Danh sách transitive đầy đủ nằm trong `backend/requirements.txt` và `backend/requirements-dev.txt`.
Dockerfile backend cài bằng `pip install --no-deps` rồi chạy `pip check`, nên thiếu hoặc lệch pin
sẽ làm build fail thay vì kéo package không ghim.

## 3. Hành vi quan trọng

### Frontend

- Mọi request dùng URL tương đối `/api/...` (`src/api/client.ts`, hằng `API_BASE = '/api'`). Bundle
  không chứa MongoDB URI, credential, hostname hay ClusterIP của backend. Test `client.test.ts` và
  `App.test.tsx` kiểm chứng mọi request đều bắt đầu bằng `/api/`.
- `nginx.conf`:
  - `GET /healthz` trả `200 ok` không đụng disk hay upstream (probe của Deployment frontend).
  - `location /api/` → `proxy_pass http://backend:8000/api/`, giữ nguyên path `/api`, forward
    `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`.
  - `location /` → `try_files $uri $uri/ /index.html` (SPA fallback); `/assets/` cache 1 năm, immutable.
  - `client_body_temp_path` và `proxy_temp_path` đặt dưới `/tmp`; base image đã đặt `pid /tmp/nginx.pid`
    và các `*_temp_path` còn lại dưới `/tmp`, nên container chạy được với `readOnlyRootFilesystem: true`
    và chỉ mount `emptyDir` vào `/tmp`.

### Backend

| Endpoint | Hành vi |
| --- | --- |
| `GET /api/health/live` | Chỉ chứng minh process/event loop còn phản hồi. **Không** gọi MongoDB. |
| `GET /api/health/ready` | `admin.command("ping")` bọc trong `asyncio.wait_for` với `MONGODB_PING_TIMEOUT_MS`; nếu unique index chưa được đảm bảo thì tạo ngay lúc này. Lỗi hoặc timeout → `503 {"detail": "MongoDB is not ready"}`. |
| `POST /api/items` | `201`; trùng `id` → `409` (dựa vào `DuplicateKeyError` của unique index, không pre-check). |
| `GET /api/items?page=&page_size=` | `200`; `page ≥ 1`, `1 ≤ page_size ≤ 100`, mặc định `1`/`20`; sort `created_at` giảm dần rồi `id`. |
| `GET /api/items/{id}` | `200` hoặc `404 {"detail": "item not found"}`. |
| `PUT /api/items/{id}` | `200`; body chỉ gồm `name`, `description`; có `id` trong body → `422`; không tồn tại → `404`. |
| `DELETE /api/items/{id}` | `204` hoặc `404`. |
| Bất kỳ thao tác DB lỗi | `503 {"detail": "database unavailable"}` (handler cho `PyMongoError`). |

Validation (`app/models.py`, trả `422` với `detail` dạng list của FastAPI):

| Field | Quy tắc |
| --- | --- |
| `id` | string, strip whitespace, 1–64 ký tự, pattern `^[A-Za-z0-9][A-Za-z0-9._~-]*$` |
| `name` | string, strip whitespace, 1–100 ký tự |
| `description` | string, strip whitespace, 0–500 ký tự, mặc định `""` |
| body | field lạ bị từ chối (`extra="forbid"`) |

Khác:

- Unique index `{id: 1}` tên `id_1` được `create_index` lúc startup; lệnh này idempotent và khớp
  đúng index mà init script MongoDB của runbook §8.1 tạo (`createIndex({ id: 1 }, { unique: true })`).
  Nếu MongoDB chưa sẵn sàng lúc startup, process vẫn lên (live = 200), readiness trả 503 và tự
  tạo index khi DB trở lại.
- Log không bao giờ chứa `MONGODB_URI`: startup chỉ log `scheme://host:port/database`
  (`redaction.describe_uri`), mọi exception của pymongo đi qua `redaction.redact` trước khi log.
- `uvicorn` là PID 1 (exec form), xử lý SIGTERM: ngừng nhận kết nối, chờ request đang chạy tối đa
  `--timeout-graceful-shutdown 20`, rồi chạy lifespan shutdown để `await client.close()`.
- Timestamps `created_at`/`updated_at` là UTC, cắt về mili giây (độ chính xác của BSON date) để
  response của POST khớp với GET sau đó.
- OpenAPI/Swagger phục vụ tại `/api/docs` và `/api/openapi.json` để đi qua được proxy.

## 4. Biến môi trường backend

| Biến | Bắt buộc | Mặc định | Nguồn trong Kubernetes |
| --- | --- | --- | --- |
| `MONGODB_URI` | có | — | Secret `backend-mongodb-uri` (runbook §9.1) |
| `MONGODB_DATABASE` | không | `cruddb` | ConfigMap `app-config` (§7.3) |
| `MONGODB_COLLECTION` | không | `items` | ConfigMap `app-config` (§7.3) |
| `MONGODB_CONNECT_TIMEOUT_MS` | không | `2000` | |
| `MONGODB_SERVER_SELECTION_TIMEOUT_MS` | không | `2000` | |
| `MONGODB_PING_TIMEOUT_MS` | không | `2000` | phải nhỏ hơn `timeoutSeconds` của readinessProbe (3 s) |
| `STARTUP_INDEX_TIMEOUT_MS` | không | `5000` | |
| `LOG_LEVEL` | không | `INFO` | |

`MONGODB_URI` dạng `mongodb://crudapp:PASSWORD_URLENCODED@mongodb:27017/cruddb?authSource=cruddb`;
password phải percent-encode trước khi ghép (runbook §9.1 dùng `urllib.parse.quote`). Thiếu biến hoặc
scheme sai → process thoát ngay với thông điệp không chứa URI.

## 5. Ví dụ API

```bash
BASE=http://127.0.0.1:8000        # local; qua Ingress dùng http://<ingress-ip> kèm Host header

curl -s "$BASE/api/health/live"
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/health/ready"

curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"id":"phase2-smoke-001","name":"Keyboard","description":"Mechanical keyboard"}'
# 201 {"id":"phase2-smoke-001","name":"Keyboard","description":"Mechanical keyboard",
#      "created_at":"2026-09-06T10:00:00Z","updated_at":"2026-09-06T10:00:00Z"}

curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"id":"phase2-smoke-001","name":"Again"}'          # 409

curl -s "$BASE/api/items?page=1&page_size=20"
curl -s "$BASE/api/items/phase2-smoke-001"
curl -s -X PUT "$BASE/api/items/phase2-smoke-001" -H 'Content-Type: application/json' \
  -d '{"name":"Keyboard v2","description":"Updated"}'
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE "$BASE/api/items/phase2-smoke-001"   # 204
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/items/phase2-smoke-001"             # 404
```

## 6. Test và build

### 6.1. Frontend (Node 24 LTS khuyến nghị; tối thiểu `^20.19.0 || >=22.12.0`)

```bash
cd frontend
npm ci                 # cài đúng lockfile, không sửa lockfile
npm test               # vitest run: api client + CRUD flow
npm run typecheck      # tsc -b
npm run build          # tsc -b && vite build → dist/
npm run dev            # dev server, proxy /api → http://127.0.0.1:8000 (chỉ khi dev)
```

`package-lock.json` là **nguồn chốt version** của frontend. Lần đầu tạo lockfile (không cài
`node_modules`):

```bash
cd frontend && npm install --package-lock-only --ignore-scripts && git add package-lock.json
```

### 6.2. Backend (Python ≥ 3.11 local; image dùng 3.13)

```bash
cd backend
python -m venv .venv
.venv/bin/pip install --no-deps -r requirements-dev.txt && .venv/bin/pip check
.venv/bin/python -m pytest
```

Trên Windows thay `.venv/bin/` bằng `.venv\Scripts\`. Test không cần MongoDB thật: `tests/fakes.py`
mô phỏng đúng subset của PyMongo Async mà app dùng, kể cả `DuplicateKeyError`,
`ServerSelectionTimeoutError` và ping treo để chứng minh timeout hữu hạn.

### 6.3. Docker (theo runbook §6.3)

```bash
docker buildx build --platform linux/amd64 --load -t "$FRONTEND_IMAGE" ./frontend
docker buildx build --platform linux/amd64 --load -t "$BACKEND_IMAGE" ./backend
docker image inspect "$FRONTEND_IMAGE" --format '{{.Architecture}} {{.Config.User}}'   # amd64 101
docker image inspect "$BACKEND_IMAGE"  --format '{{.Architecture}} {{.Config.User}}'   # amd64 10001:10001
```

Cả hai Dockerfile chạy unit test trong stage build/test và stage runtime copy artefact từ stage đó,
nên **build chỉ thành công khi test pass**. Chỉ chạy test không tạo image runtime:

```bash
docker build --target build ./frontend
docker build --target test  ./backend
```

`npm ci` và `pip install` chỉ chạy trong stage build của Dockerfile; không có bước cài đặt nào
trên máy host.

### 6.4. Chạy backend local (tùy chọn)

```bash
cd backend
MONGODB_URI='mongodb://127.0.0.1:27017/cruddb' .venv/bin/uvicorn app.main:create_app --factory \
  --host 0.0.0.0 --port 8000
```

## 7. Bảo mật và supply chain

- Frontend chạy uid 101 (`nginx`), backend chạy uid/gid 10001 (`app`, không home, `nologin`);
  `Config.User` của cả hai image là số nên `runAsNonRoot: true` xác minh được.
- Không cần `privileged`, không cần capability; hai container tương thích với
  `readOnlyRootFilesystem: true` khi mount `emptyDir` vào `/tmp` (đúng manifest §9.2 và §10.1).
  Backend đặt `PYTHONDONTWRITEBYTECODE=1` nên không ghi `.pyc` vào rootfs.
- Base image pin tag phiên bản cụ thể; runbook §6.4 pin thêm digest khi deploy.
- `npm ci --ignore-scripts`: không chạy lifecycle script của dependency khi build.
- Không có secret trong repo: URI test không chứa credential; test redaction ghép URI lúc chạy.
  Kiểm tra bằng source gate của runbook §5.3:

```bash
git ls-files | grep -Ei '(^|/)(\.env|.*secret.*|.*credential.*)$' || true
grep -RInE 'mongodb://[^[:space:]]+:[^[:space:]@]+@|MONGO_INITDB_ROOT_PASSWORD=' . \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist --exclude='*.md' || true
```

## 8. Thư mục `k8s/`

Cố ý rỗng (`.gitkeep`). Manifest tại §8–§11 của `runbook-k8s-vmware-phase2.md` là source of truth;
sau khi source gate §5.3 và build §6 PASS, operator chép nguyên văn vào `k8s/` và chỉ thay
`CHANGE_ME_*_IMAGE_PINNED` cùng domain. Repo này không tự thiết kế manifest.
