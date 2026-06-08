# Đề tài #49: Nghiên Cứu Hệ Thống Phân Tán — Eager vs Lazy Replication

Mô phỏng hai chiến lược replication **Eager (đồng bộ)** và **Lazy (bất đồng bộ)** trong hệ thống cơ sở dữ liệu phân tán, dựa trên lý thuyết của Özsu & Valduriez. Hệ thống sử dụng **Transaction Ledger** làm kịch bản nghiên cứu.

## Kiến trúc hệ thống

```
┌──────────────┐     ┌──────────────────────────────────────┐
│   Browser    │────▶│  Node_A_Primary (FastAPI :8001)      │
│ (Dashboard)  │     │  - Nhận write từ client              │
└──────────────┘     │  - Điều phối replication (eager/lazy)│
                     │  - Table: node_a                      │
                     └───────────┬──────────────────────────┘
                                 │ replicate
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
        ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
        │ Node_B_Replica   │ │ Node_C_Replica   │ │   MySQL 8.0      │
        │ (FastAPI :8002)  │ │ (FastAPI :8003)  │ │   (port 3306)    │
        │ Table: node_b    │ │ Table: node_c    │ │                  │
        └────────┬─────────┘ └────────┬─────────┘ │ replication_db   │
                 │                    │           │ node_a, node_b,  │
                 └────────────────────┘           │ node_c tables    │
                                                  └──────────────────┘
```

- **1 Primary node** (Node A) — nhận ghi, chịu trách nhiệm replication
- **2 Replica nodes** (Node B, C) — nhận dữ liệu nhân bản
- **MySQL 8.0** — lưu trữ tập trung, mỗi node có table riêng
- Dashboard real-time tại `http://localhost:8001/`

## Cơ chế Replication

### Eager (Đồng bộ)
Primary chờ tất cả replica xác nhận ghi thành công **trước khi** trả response cho client. Đảm bảo tính nhất quán mạnh (strong consistency) nhưng độ trễ cao hơn.

### Lazy (Bất đồng bộ)
Primary trả response ngay sau khi ghi local, replication diễn ra trong background task. Có độ trễ thấp, throughput cao hơn, nhưng replica có thể chưa cập nhật ngay lập tức.

## Yêu cầu

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (kèm Compose)

## Chạy hệ thống

```bash
docker compose up -d --build
```

Sau đó mở dashboard tại: [http://localhost:8001/](http://localhost:8001/)

## Dashboard

Dashboard cho phép:
- **Giám sát real-time** số dòng dữ liệu của từng node (tự động cập nhật mỗi giây)
- **Chạy benchmark** với số lượng giao dịch tuỳ chọn (0–10,000), chọn chế độ Eager hoặc Lazy
- **So sánh TPS** (transactions per second) giữa hai chế độ qua biểu đồ cột
- **Reset** toàn bộ dữ liệu trên tất cả node

## API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/` | Dashboard HTML |
| POST | `/write?mode=eager\|lazy` | Ghi transaction với chế độ replication |
| POST | `/replicate` | Replica nhận dữ liệu từ primary |
| GET | `/check/{id}` | Kiểm tra transaction có tồn tại trên node không |
| GET | `/metrics` | Số lượng bản ghi hiện tại trên node |
| GET | `/data?limit=N` | Danh sách transaction gần nhất |
| POST | `/reset-local` | Xoá dữ liệu trên node hiện tại |
| POST | `/reset-all` | Xoá dữ liệu trên tất cả node (chỉ primary) |

## Lệnh hữu ích

```bash
# Dừng toàn bộ
docker compose down

# Reset dữ liệu qua API
curl -X POST http://localhost:8001/reset-all

# Build lại sau khi sửa code
docker compose down
docker compose up -d --build
```

## Ghi chú

- Dữ liệu MySQL được lưu trong volume `mysql_data`
- File `.dockerignore` giúp build image nhanh hơn
- Các node giao tiếp qua mạng bridge nội bộ `replication_nw`
