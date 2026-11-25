# Phát hành: robot_diag_ui

Công cụ chẩn đoán nội bộ (Python + web UI), **không phát hành qua fwhub-server**: không có `release.config.json`, không có sản phẩm trong danh mục server.
Vẫn theo chuẩn chung `06_Repositories/_standards/RELEASE-BUILDS.md`:

- Mọi file build, báo cáo, tạm thời đặt ở `outputs/` (`outputs/temporary/` đã được git bỏ qua). Bản đóng gói `scripts\build_exe.ps1` là bản **LOCAL**, chỉ dùng trong nhóm.
- CI (`bitbucket-pipelines.yml`) chỉ chạy `scripts\check.ps1` trên PR, `develop`, `main`, `release/*` và tag; không build bản phát hành, không upload.
- Muốn phát hành có kiểm soát như firmware/app: thêm product vào `fwhub-server/catalog/products.json`, `release.config.json` và builder tương ứng (chưa có builder cho Python/PyInstaller).
