# LocalSend for RISC-V 64 (riscv64)

LocalSend 的 riscv64 构建适配 —— 含**完整桌面 GUI**。

已在 **SpacemiT K3 (Bianbu 4.0.1, kernel 6.18.3, riscv64)** 上实测：GUI 编译成功、窗口正常渲染、
设备发现、HTTPS 收发文件、中文本地化全部打通。

![LocalSend GUI on riscv64](screenshots/02-release.png)

---

## ⚠️ 先读这一段：本仓库**不包含** Flutter 引擎

LocalSend 的桌面 GUI 是 Flutter 应用，而 **Flutter 官方不发布任何 riscv64 Linux 引擎产物**。

所以：

| 你要什么 | 需要什么 |
|---|---|
| **CLI + 网页直传** | 只要 Rust 工具链，`scripts/build-riscv64.sh` 直接能编 |
| **完整桌面 GUI** | **必须自己有 riscv64 Flutter 引擎**，见 [`docs/01-引擎前提.md`](docs/01-引擎前提.md) |

本仓库提供的是**适配层**：补丁、构建脚本、打包配置、以及踩过的坑。
它不含、也不能含 425 MB 的引擎二进制。

如果你没有自建引擎，GUI 这条路会停在：

```
ERROR: Target aot_snapshot_release failed:
  Failed to find ".../bin/cache/artifacts/engine/linux-riscv64-release/gen_snapshot"
```

---

## 已验证的成果

| 项目 | 结果 |
|---|---|
| GUI 编译（debug） | ✅ bundle 657 MB，`kernel_blob.bin` 运行时 JIT |
| GUI 编译（release AOT） | ✅ bundle 67 MB，`libapp.so` 15.7 MB，242 秒 |
| 窗口渲染 | ✅ 1024–1026 ms 出现，940 色，品牌绿在位 |
| 设备发现 | ✅ 认出 `聪明的椰子 (10.5.90.193, model: Redmi)` |
| **端到端传文件** | ✅ 296,031 B JPEG，MD5 双向一致，原始 mtime 保留 |
| 中文本地化 | ✅ 设备名「明亮的覆盆子」 |
| deb 打包 | ✅ 20.5 MB，`dpkg -i` 退出码 0，依赖零缺失，desktop 校验干净 |

### 未验证

- 反向发送（板子 → 手机）
- 大文件（只测了 289 KB）、多文件、文件夹
- 断点续传、失败重试
- 托盘图标实际显示（测试环境是 Xvfb，无系统托盘）
- **真实 Xorg / Wayland 下的显示**（全程 Xvfb + llvmpipe）

---

## 安装（从 deb）

```bash
sudo dpkg -i localsend-gui-riscv64_1.18.2_riscv64.deb
localsend-gui
```

包结构：

```
/opt/localsend-gui/                  67 MB
├── localsend_app                    ELF64 RISC-V
├── lib/libapp.so                    AOT 机器码 15.7 MB
├── lib/libflutter_linux_gtk.so      自建引擎 14 MB
├── lib/librust_lib_localsend_app.so Rust core 24 MB
└── data/icudtl.dat + flutter_assets/

/usr/local/bin/localsend-gui
/usr/share/applications/localsend-gui.desktop
/usr/share/icons/hicolor/256x256/apps/localsend-gui.png
```

可与 CLI 版包 `localsend-riscv64` 共存（两个包共用 53317 端口，但同时只能跑一个）。

---

## 从源码构建

### CLI + 网页直传（不需要 Flutter）

```bash
git clone https://github.com/localsend/localsend.git
cd localsend
./scripts/build-riscv64.sh          # Rust core + CLI + link
./scripts/package-deb.sh            # 4.6 MB deb
```

### GUI（需要自建引擎）

```bash
export FLUTTER_ROOT=/path/to/flutter-tool
export ENGINE_SRC=/path/to/engine/src

# 1. 打补丁
cd app
git apply ../../patches/0002-cmake-no-error-deprecated.patch

# 2. 构建（必须带 --local-engine，见 docs/01）
flutter build linux --release --no-tree-shake-icons \
  --local-engine-src-path=$ENGINE_SRC \
  --local-engine=riscv64-release \
  --local-engine-host=riscv64-release
```

Rust 部分还需要 `patches/0001-cargokit-riscv64.patch`。

---

## 仓库结构

```
docs/
  01-引擎前提.md        自建引擎需要什么、当前缺口在哪
  02-GUI构建记录.md     从零到 GUI 的完整过程
  03-deb打包.md         包结构、依赖计算、安装测试
  04-端到端验证.md      传输验证的日志与数据
  05-踩坑清单.md        10 个坑的根因与解法
patches/
  0001-cargokit-riscv64.patch           cargokit 认 riscv64
  0002-cmake-no-error-deprecated.patch  弃用警告不升错误
  0003-上游建议版.md                    推上游时应改用的标准 triple
packaging/deb/        control / postinst / launcher / desktop
scripts/              CLI 构建、deb 打包、5 个验证脚本
screenshots/          三张运行截图
engine-notes/         gen_snapshot 包装脚本（AOT hash 修正）
```

---

## 一个必须知道的坑

补丁 `0001` 里用的是 **`riscv64a23-unknown-linux-gnu`** —— 这是 SpacemiT 定制工具链的
私有 triple，**不通用**。

之所以用它：板子的 `rustc -vV` 报 `host: riscv64a23-unknown-linux-gnu`，
且 `$(rustc --print sysroot)/lib/rustlib/` 下**只有这一个 triple 有 std**，系统没装 rustup。

**推上游 / 换通用环境请用** `riscv64gc-unknown-linux-gnu`，见
[`patches/0003-上游建议版.md`](patches/0003-上游建议版.md)。

---

## License

[Apache License 2.0](LICENSE) —— 与上游 [localsend/localsend](https://github.com/localsend/localsend) 一致。

本仓库的适配内容（补丁、脚本、文档）同样以 Apache 2.0 发布。

上游源码本身不在本仓库内，请从其官方仓库获取。
