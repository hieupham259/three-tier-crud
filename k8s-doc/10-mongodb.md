# MongoDB trên Kubernetes

Tài liệu này giải thích toàn bộ [`10-mongodb.yaml`](10-mongodb.yaml): mỗi tài nguyên được tạo ra, cách các trường YAML nối với nhau, và vì sao quá trình khởi tạo dùng đồng thời ConfigMap và Secret.

## Cách đọc manifest

File có ba tài nguyên, ngăn cách bằng `---`:

| Tài nguyên | Tên | Vai trò |
| --- | --- | --- |
| `Service` | `mongodb` | Tạo tên mạng và chọn Pod MongoDB làm đích kết nối. |
| `ConfigMap` | `mongodb-init` | Chứa script tạo user ứng dụng và unique index. |
| `StatefulSet` | `mongodb` | Chạy một Pod MongoDB, gắn script và lưu dữ liệu trên PVC. |

`apiVersion` xác định phiên bản API của tài nguyên; `kind` xác định loại tài nguyên; `metadata` chứa tên, namespace và nhãn; `spec` mô tả trạng thái mong muốn. Riêng ConfigMap dùng `data` để chứa nội dung thay vì `spec`. Thụt lề trong YAML thể hiện trường nào thuộc trường nào; dấu `-` mở một phần tử trong danh sách.

Cả ba tài nguyên đều nằm trong namespace `three-tier`. Manifest **không tạo namespace** này. Nó cũng **không tạo Secret** `mongodb-credentials` hoặc StorageClass `local-path`; các đối tượng được tham chiếu đó phải có sẵn khi Pod cần dùng.

## 1. Service: cách tìm đúng Pod

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mongodb
  namespace: three-tier
  labels:
    app.kubernetes.io/name: mongodb
spec:
  clusterIP: None
  selector:
    app.kubernetes.io/name: mongodb
  ports:
    - name: mongodb
      port: 27017
      targetPort: mongodb
```

`metadata.name` đặt tên **đối tượng Service** là `mongodb`. Pod khác trong namespace `three-tier` có thể dùng `mongodb:27017` để tìm MongoDB. Tên DNS đầy đủ thường là `mongodb.three-tier.svc.cluster.local`, nếu cluster dùng miền mặc định `cluster.local`.

`metadata.labels` gắn nhãn **lên chính Service** để quản lý hoặc tìm kiếm đối tượng. Toàn bộ chuỗi `app.kubernetes.io/name` là tên của một label key; `mongodb` là giá trị của key đó. Nhãn này không quyết định Service chọn Pod nào.

`spec` của Service là phần quy định cách Service hoạt động. Bên trong nó:

- `clusterIP: None` tạo **headless Service**: Service không có IP ảo riêng; DNS trả về IP của những Pod phù hợp và sẵn sàng. Headless Service cũng cung cấp miền mạng ổn định cho StatefulSet. Vì không khai báo `type`, loại Service vẫn là `ClusterIP` mặc định, với giá trị `clusterIP` đặc biệt là `None`. File không tạo điểm truy cập MongoDB từ bên ngoài cluster.
- `spec.selector` là điều kiện **chọn Pod làm endpoint của Service**. Nó tìm Pod trong cùng namespace có nhãn `app.kubernetes.io/name=mongodb`. Kubernetes so điều kiện này với **nhãn trên Pod**, không so với `metadata.labels` của Service hoặc tên container.
- `spec.ports` là danh sách cổng Service công bố; ở đây có một cổng. `name: mongodb` đặt tên cổng Service; `port: 27017` là cổng client dùng; `targetPort: mongodb` tham chiếu cổng **có tên `mongodb` trên Pod**. Container khai báo cổng đó ở số `27017`, nên lưu lượng đi đến cổng 27017 của Pod. Giao thức mặc định là TCP.

Mối nối bằng nhãn trong file:

```text
Service.spec.selector: app.kubernetes.io/name=mongodb
                           │ khớp với
                           ▼
StatefulSet.spec.template.metadata.labels: app.kubernetes.io/name=mongodb
                           │ tạo ra Pod mang nhãn này
                           ▼
                       mongodb-0
```

Nếu nhãn trên Pod không khớp `Service.spec.selector`, Service sẽ không chọn Pod đó dù cả Service và StatefulSet đều tên `mongodb`.

## 2. ConfigMap và Secret: script cần cả mã lệnh lẫn thông tin đăng nhập

Đây là điểm quan trọng nhất của manifest. **ConfigMap chứa cách khởi tạo**, còn **Secret cung cấp các giá trị đăng nhập để thực hiện cách khởi tạo đó**. Hai đối tượng có vai trò khác nhau:

| Nguồn | Nội dung | Cách container nhận |
| --- | --- | --- |
| ConfigMap `mongodb-init` | Script `.sh`: đăng nhập root, tạo user ứng dụng, tạo index. Script chỉ nhắc đến *tên* biến môi trường, không chứa mật khẩu thật. | Gắn thành file trong `/docker-entrypoint-initdb.d/`. |
| Secret `mongodb-credentials` | Tên user và mật khẩu root/ứng dụng. | `envFrom.secretRef` biến các key của Secret thành biến môi trường trong container. |
| `env` trong StatefulSet | Hai giá trị không bí mật: `MONGO_INITDB_DATABASE=cruddb` và `MONGO_APP_DATABASE=cruddb`. | Khai báo trực tiếp trên container. |

ConfigMap dành cho dữ liệu không bí mật; không nên đưa mật khẩu vào script của nó. Secret là loại tài nguyên Kubernetes dành cho dữ liệu nhạy cảm, nhưng vẫn cần phân quyền truy cập phù hợp; Secret không mặc nhiên được mã hóa khi lưu trong etcd.

Manifest này **chỉ tham chiếu** Secret `mongodb-credentials`, không định nghĩa Secret đó. Để đúng với những chỗ sử dụng trong file, Secret cùng namespace `three-tier` cần có ít nhất các key sau:

| Key của Secret | Ai dùng | Mục đích |
| --- | --- | --- |
| `MONGO_INITDB_ROOT_USERNAME` | Entrypoint image MongoDB và script | Tạo rồi đăng nhập root user trong database `admin`. |
| `MONGO_INITDB_ROOT_PASSWORD` | Entrypoint image MongoDB và script | Mật khẩu root. |
| `MONGO_APP_USERNAME` | Script | Tên user ứng dụng được tạo trong `cruddb`. |
| `MONGO_APP_PASSWORD` | Script | Mật khẩu user ứng dụng. |

Đường đi của dữ liệu:

```text
ConfigMap mongodb-init ──gắn file──> /docker-entrypoint-initdb.d/01-create-app-user.sh
                                               │ chạy khi dữ liệu mới
                                               ▼
Secret mongodb-credentials ──envFrom──> biến môi trường trong container
                                               │ process.env đọc giá trị
                                               ▼
                                  tạo user và index trong MongoDB
```

Nếu bỏ `secretRef`, script vẫn có mặt trong container nhưng thiếu tên user/mật khẩu để làm việc. Image MongoDB cũng thiếu cặp biến root cần cho việc tạo tài khoản quản trị. Nếu bỏ ConfigMap hoặc volume gắn script, image có thể tạo root user từ Secret, nhưng **không có các lệnh trong file này** để tạo user ứng dụng và index.

### Từng phần của ConfigMap và script

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mongodb-init
  namespace: three-tier
data:
  01-create-app-user.sh: |
    ...
```

`data` chứa các cặp key–value dạng văn bản. `01-create-app-user.sh` là key và cũng là tên file khi được gắn vào container. Dấu `|` giữ các dòng bên dưới thành một chuỗi nhiều dòng. Kubernetes lưu nội dung này; **entrypoint của image MongoDB** mới là thành phần chạy script. Tiền tố `01-` xác định thứ tự nếu có thêm file khởi tạo.

```bash
#!/bin/bash
set -eu
mongosh --quiet --host 127.0.0.1 <<'EOF'
```

- `#!/bin/bash` đánh dấu script Bash. Entrypoint của image MongoDB nạp (`source`) file `.sh` trong thư mục khởi tạo, nên file không cần quyền thực thi.
- `set -e` làm shell dừng khi một lệnh thất bại; `set -u` báo lỗi khi dùng biến shell chưa được đặt.
- `mongosh --quiet` mở MongoDB shell và giảm thông báo thông thường. `--host 127.0.0.1` kết nối tới MongoDB trong **cùng container**, không qua Service Kubernetes.
- `<<'EOF'` gửi mọi dòng từ đây đến dòng `EOF` cuối script vào `mongosh`. Dấu nháy quanh `'EOF'` ngăn Bash thay thế nội dung trong khối; các biểu thức `process.env...` được JavaScript trong `mongosh` đọc từ môi trường.

```javascript
const adminDb = db.getSiblingDB("admin")
if (!adminDb.auth(
  process.env.MONGO_INITDB_ROOT_USERNAME,
  process.env.MONGO_INITDB_ROOT_PASSWORD
)) {
  throw new Error("MongoDB root authentication failed")
}
```

`getSiblingDB("admin")` lấy đối tượng tham chiếu database `admin`, nơi root user của image được tạo. `process.env...` lấy hai giá trị do Secret cung cấp. `adminDb.auth(...)` đăng nhập bằng root; dấu `!` biến kết quả thất bại thành điều kiện đúng và `throw new Error(...)` báo lỗi khởi tạo. Image MongoDB sử dụng cùng cặp biến `MONGO_INITDB_ROOT_*` để tạo root user khi thư mục dữ liệu còn mới.

```javascript
const appDb = db.getSiblingDB(process.env.MONGO_APP_DATABASE)
appDb.createUser({
  user: process.env.MONGO_APP_USERNAME,
  pwd: process.env.MONGO_APP_PASSWORD,
  roles: [{ role: "readWrite", db: process.env.MONGO_APP_DATABASE }]
})
```

`MONGO_APP_DATABASE` được đặt thành `cruddb` trong `env`, nên `appDb` trỏ đến database đó. `createUser` tạo user ứng dụng bằng tên/mật khẩu từ Secret. Role `readWrite` cấp quyền đọc và ghi trên `cruddb`; ứng dụng không cần dùng tài khoản root. Vì user được tạo trong `cruddb`, client dùng user này cần xác thực với database đó, chẳng hạn URI có `authSource=cruddb`.

```javascript
appDb.items.createIndex({ id: 1 }, { unique: true })
```

`items` là collection; `{ id: 1 }` tạo index tăng dần theo trường `id`; `{ unique: true }` ngăn hai tài liệu có cùng giá trị `id`. Dòng `EOF` sau đó kết thúc phần đầu vào của `mongosh`.

**Thời điểm chạy:** entrypoint image MongoDB chạy file trong `/docker-entrypoint-initdb.d/` khi khởi tạo một thư mục dữ liệu MongoDB mới. Khi PVC đã chứa dữ liệu, restart Pod hoặc sửa ConfigMap **không tự chạy lại** `createUser`/`createIndex`. Đổi giá trị Secret cũng không tự đổi mật khẩu của user đã tồn tại trong MongoDB; biến môi trường lấy từ Secret chỉ được đưa vào container khi nó bắt đầu chạy.

## 3. StatefulSet: Pod, môi trường, kiểm tra sức khỏe và lưu trữ

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mongodb
  namespace: three-tier
  labels:
    app.kubernetes.io/name: mongodb
spec:
  serviceName: mongodb
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: mongodb
  template:
    metadata:
      labels:
        app.kubernetes.io/name: mongodb
```

`apps/v1` là API của StatefulSet. `metadata.name` đặt tên StatefulSet; `metadata.labels` gắn nhãn lên **chính StatefulSet**. `spec.serviceName: mongodb` liên kết StatefulSet với headless Service cùng tên để hình thành danh tính mạng ổn định. `replicas: 1` tạo một Pod, thường là `mongodb-0`; cấu hình này chưa thiết lập MongoDB replica set.

`StatefulSet.spec.selector.matchLabels` cho controller biết **Pod nào thuộc quyền quản lý của StatefulSet**. Nó phải khớp `spec.template.metadata.labels`, là nhãn thực sự gắn lên Pod được tạo. Đây là selector **khác** `Service.spec.selector`: selector của StatefulSet dùng để quản lý Pod; selector của Service dùng để chọn Pod làm endpoint mạng. Cả hai cùng khớp nhãn trong Pod template.

### Cấu hình Pod và container

`spec.template.spec` là cấu hình của Pod được tạo từ template:

| Trường | Ý nghĩa |
| --- | --- |
| `terminationGracePeriodSeconds: 60` | Cho container tối đa 60 giây để dừng êm trước khi bị buộc dừng. |
| `automountServiceAccountToken: false` | Không tự gắn token truy cập Kubernetes API vào Pod. |
| `containers` | Danh sách container; ở đây chỉ có một container tên `mongodb`. |
| `image: docker.io/library/mongo:8.0.29-noble` | Image MongoDB và tag được chọn. |
| `imagePullPolicy: IfNotPresent` | Dùng image trên node nếu đã có; nếu chưa có, kubelet cần lấy image. |
| `ports[0].name: mongodb` | Tên cổng container mà `Service.spec.ports[0].targetPort` tham chiếu. |
| `ports[0].containerPort: 27017` | Số cổng MongoDB trong container. |

Biến môi trường được khai báo theo hai cách:

```yaml
env:
  - name: MONGO_INITDB_DATABASE
    value: cruddb
  - name: MONGO_APP_DATABASE
    value: cruddb
envFrom:
  - secretRef:
      name: mongodb-credentials
```

`env` đặt trực tiếp hai giá trị không bí mật. `MONGO_APP_DATABASE` được script đọc. `MONGO_INITDB_DATABASE` là biến của image MongoDB, dùng làm database mặc định cho các file khởi tạo `.js`; script hiện tại là `.sh` và tự chọn database bằng `getSiblingDB(...)`. Chỉ đặt `MONGO_INITDB_DATABASE` **không tự tạo user ứng dụng hoặc index**. `envFrom.secretRef` đưa các key trong Secret thành biến môi trường cùng tên, để cả entrypoint lẫn script đọc được. Secret phải ở cùng namespace với Pod.

### Hai volume được gắn vào container

```yaml
volumeMounts:
  - name: data
    mountPath: /data/db
  - name: init
    mountPath: /docker-entrypoint-initdb.d/01-create-app-user.sh
    subPath: 01-create-app-user.sh
    readOnly: true
```

- `data` gắn PVC vào `/data/db`, nơi MongoDB lưu dữ liệu. Nguồn của nó là `volumeClaimTemplates` phía dưới.
- `init` gắn một key của ConfigMap thành đúng file script trong thư mục mà image MongoDB quét khi khởi tạo. `subPath` chọn riêng key `01-create-app-user.sh` thay vì gắn toàn bộ ConfigMap đè lên thư mục. `readOnly: true` không cho container ghi vào file script.

Nguồn của volume `init` được khai báo ở cấp `spec.template.spec`, cùng cấp với `containers`:

```yaml
volumes:
  - name: init
    configMap:
      name: mongodb-init
      defaultMode: 0444
```

`name: init` nối với `volumeMounts.name: init`; `configMap.name` trỏ đến ConfigMap ở phần 2. `defaultMode: 0444` cấp quyền đọc, không cấp quyền ghi/thực thi. Entrypoint image MongoDB nạp file `.sh` nên không cần cờ thực thi.

### Ba probe

| Probe | Cách kiểm tra | Chu kỳ, timeout, ngưỡng lỗi | Hệ quả khi thất bại liên tiếp |
| --- | --- | --- | --- |
| `startupProbe` | Chạy `mongosh --quiet --eval "db.adminCommand('ping').ok"` trong container. | 5 giây; 5 giây; 30 lần. | Container bị khởi động lại nếu không hoàn tất khởi động trong ngưỡng. Khi startup probe chưa thành công, readiness và liveness chưa quyết định trạng thái theo cách thông thường. |
| `readinessProbe` | Chạy cùng lệnh `mongosh`/`ping`. | 15 giây; 5 giây; 4 lần. | Pod bị đánh dấu chưa sẵn sàng, nên không được dùng như endpoint sẵn sàng của Service. |
| `livenessProbe` | Mở kết nối TCP đến cổng có tên `mongodb` (27017). | 30 giây; 3 giây; 6 lần. | Kubelet khởi động lại container. |

`periodSeconds` là khoảng cách giữa các lần kiểm tra; `timeoutSeconds` là giới hạn thời gian mỗi lần; `failureThreshold` là số lần thất bại liên tiếp cần đạt. Liveness chỉ kiểm tra cổng TCP; các probe này không thử đăng nhập bằng user ứng dụng hoặc đọc/ghi `cruddb`. Với probe kiểu `exec`, Kubernetes xét **mã thoát của `mongosh`**; biểu thức `.ok` không tự tạo một điều kiện `exit(1)` tường minh khi giá trị khác `1`.

### CPU và RAM

```yaml
resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: "1"
    memory: 1536Mi
```

`requests` là mức tài nguyên Kubernetes dùng khi xếp Pod lên node: `250m` bằng 0,25 CPU, RAM là 512 MiB. `limits` đặt trần 1 CPU và 1536 MiB RAM. Vượt giới hạn RAM có thể khiến container bị chấm dứt do thiếu bộ nhớ.

### PVC và PV

```yaml
volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: local-path
      resources:
        requests:
          storage: 10Gi
```

`volumeClaimTemplates` là **mẫu tạo PVC cho mỗi Pod StatefulSet**. Với `mongodb-0`, PVC thường tên `data-mongodb-0`; tên `data` nối với `volumeMounts.name: data`. PVC yêu cầu 10 GiB từ StorageClass `local-path`. `ReadWriteOnce` cho phép volume được gắn đọc/ghi bởi một node tại một thời điểm; nó không có nghĩa mỗi volume chỉ có đúng một tiến trình đọc/ghi.

Manifest **có Service và mẫu tạo PVC**, nhưng **không khai báo PV trực tiếp**. Nếu `local-path` có provisioner đang hoạt động, provisioner có thể cấp PV để đáp ứng PVC. Nếu StorageClass không tồn tại, không cấp phát động, hoặc không có PV phù hợp, PVC sẽ không chuyển sang `Bound`. Với `volumeBindingMode: WaitForFirstConsumer`, PVC có thể tạm `Pending` cho đến khi Pod dùng nó được lên lịch. PVC giữ dữ liệu qua vòng đời Pod; nó không thay thế bản sao lưu. Vì file chỉ định rõ `storageClassName: local-path`, StorageClass này không cần là default của cluster.

## Diễn biến khi triển khai

1. Service `mongodb` và ConfigMap `mongodb-init` được tạo trong namespace `three-tier`.
2. StatefulSet tạo Pod `mongodb-0` và PVC `data-mongodb-0` từ mẫu `volumeClaimTemplates`.
3. Container nhận các biến trực tiếp từ `env`, thông tin đăng nhập từ Secret qua `envFrom`, file script từ ConfigMap qua volume `init`, và vùng dữ liệu từ PVC qua volume `data`.
4. Nếu `/data/db` là thư mục dữ liệu mới, entrypoint MongoDB tạo root user, chạy script để tạo user ứng dụng và unique index, rồi khởi chạy MongoDB bình thường.
5. Khi Pod vượt qua readiness probe, Service chọn Pod theo label và client trong cluster có thể kết nối đến `mongodb:27017`.

Để kiểm tra phần lưu trữ sau khi triển khai:

```text
kubectl get storageclass local-path -o wide
kubectl get pvc -n three-tier
kubectl describe pvc -n three-tier data-mongodb-0
kubectl get pv
```

PVC `data-mongodb-0` ở trạng thái `Bound` và có tên PV trong cột `VOLUME` là dấu hiệu yêu cầu lưu trữ đã được đáp ứng. Nếu PVC ở `Pending`, xem mục `Events` của `kubectl describe pvc` và trạng thái Pod `mongodb-0` để tìm nguyên nhân.

## Tài liệu tham khảo

- [Kubernetes Service, selector và headless Service](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Kubernetes ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/) và [Secret](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes StorageClass](https://kubernetes.io/docs/concepts/storage/storage-classes/) và [dynamic provisioning](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/)
- [Cách image MongoDB chạy script khởi tạo](https://github.com/docker-library/docs/blob/master/mongo/content.md#initializing-a-fresh-instance)
