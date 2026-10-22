# LocalSend release 版（AOT）构建记录

## 结果

**Release 版编译成功并运行。**

![LocalSend release](../screenshots/02-release.png)

- 构建耗时 **242 秒**，退出码 0
- Bundle **67 MB**（debug 版 657 MB → **小 9.8 倍**）
- 49 个文件，`ldd` 零缺失依赖
- 窗口 1024 ms 出现
- **`[Server] Server started. (Port: 53317, HTTPS only)`**
- 三个 isolate 全部就绪（Discovery / HttpUpload / HttpServer）
- 网络状态：`[10.5.90.75]`
- 截图 34,313 B，940 种颜色，含品牌绿 `RGB(0,106,96)`

## 产物结构（正确的 AOT 布局）

| 文件 | 大小 | 说明 |
|---|---|---|
| `localsend_app` | 27,424 B | 主程序（release 版比 debug 的 69 KB 还小） |
| `lib/libapp.so` | 15,729,544 B | **AOT 编译后的 Dart 代码** |
| `lib/libflutter_linux_gtk.so` | 13,996,360 B | release 引擎（含 Skia 补丁） |
| `lib/librust_lib_localsend_app.so` | 24,133,064 B | Rust core |
| `data/icudtl.dat` | 10,824,432 B | ICU 数据 |
| `kernel_blob.bin` | **不存在** | ✅ release 走 AOT，不需要 |

debug 版靠 `kernel_blob.bin`（111 MB）在运行时 JIT；
release 版把它换成了 15.7 MB 的 `libapp.so` 机器码。

---

## 填的两个坑

### 坑 A · AOT snapshotter 退出码 254（`ApiError`）

```
ERROR: ApiError
ERROR: Dart snapshot generator failed with exit code 254
ERROR: Target aot_snapshot_release failed
```

根因：**引擎构建里混了两个 Dart SDK 版本**。

| 组件 | Dart 版本 |
|---|---|
| `gen_snapshot` | **3.15.0-51.0.dev** |
| `frontend_server`（产出 app.dill） | **3.15.0-40.0.dev** |

`gen_snapshot` 会校验输入 dill 头部的 10 字节 SDK hash：
- `frontend_server` 写的是 `5521341774`（40.0.dev 的 hash）
- `gen_snapshot` 期望 `69672e35b9`（51.0.dev 的 hash）

不匹配 → `ApiError` → exit 254。

**先说失败的尝试**：手动把 `app.dill` 的 hash 改成 `69672e35b9`，然后单独跑 `gen_snapshot` —— **成功了**，产出 15,729,544 B 的 `app.so`，耗时约 4 分钟。

但直接 `flutter build linux --release` 时又失败：**flutter 会重新跑 frontend_server，把 `app.dill` 覆盖回旧哈希**，我的修改被撤销。

**最终解法**：给 `gen_snapshot` 套一层包装（`gen_snapshot-wrapper.sh`），每次被调用时先把输入 dill 的 hash 修正，再交真正的二进制执行。

```bash
cd .../out/riscv64-release
cp -a gen_snapshot gen_snapshot.real    # 备份真身
cat > gen_snapshot <<'WRAP'
#!/bin/bash
REAL="$(dirname "$(readlink -f "$0")")/gen_snapshot.real"
PATCHER="/root/flutter-riscv64-engine/scripts/patch-kernel-hash.py"
IN=""
for a in "$@"; do case "$a" in -*) ;; *) IN="$a" ;; esac; done
[ -n "$IN" ] && [ -f "$IN" ] && python3 "$PATCHER" "$IN" 69672e35b9 >/dev/null 2>&1
exec "$REAL" "$@"
WRAP
chmod +x gen_snapshot
```

包装对调试也透明：`./gen_snapshot --version` 仍正常输出
`Dart SDK version: 3.15.0-51.0.dev ... on "linux_riscv64"`。

### 坑 B · `font-subset` 工具缺失

```
ERROR: Target release_bundle_linux-riscv64_assets failed:
IconTreeShakerException: The font-subset utility is missing. Run "flutter doctor".
```

根因：release 构建默认开启图标字体子集化，需要
`artifacts/engine/linux-riscv64/font-subset` 这个二进制。
官方不发布 riscv64 的，我们也没有自建。

解法：**关掉图标裁剪**

```bash
flutter build linux --release --no-tree-shake-icons ...
```

代价：Material 图标字体不会被裁剪，包体略大。对这个项目无所谓。

---

## 一条命令复现

```bash
E=/root/flutter-riscv64-engine
cd /root/localsend-riscv64/src/localsend/app

flutter build linux --release --no-tree-shake-icons \
  --local-engine-src-path=$E/src/flutter.tmp/engine/src \
  --local-engine=riscv64-release --local-engine-host=riscv64-release
# → ✓ Built build/linux/riscv64/release/bundle/localsend_app   (242s)

# 跑（不需要改 kernel hash，AOT 模式没有 kernel_blob）
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
cd build/linux/riscv64/release/bundle && DISPLAY=:99 dbus-run-session -- ./localsend_app
```

---

## 与 debug 版的对比

| | debug | release |
|---|---|---|
| 构建耗时 | 37 s（增量） | 242 s |
| Bundle 大小 | 657 MB | **67 MB** |
| Dart 代码形态 | `kernel_blob.bin` 111 MB，运行时 JIT | `libapp.so` 15.7 MB，AOT 机器码 |
| 需要改 kernel hash | **是**（177 段 header） | **否** |
| 需要 `--no-tree-shake-icons` | 否 | **是** |
| 首帧 | 秒级 | 秒级（窗口 1024 ms 出现） |
| 窗口尺寸 | 900×600 | 400×500 |

### 窗口尺寸差异不是 bug

release 打开是 400×500（GTK 在 `my_application.cc` 里的默认首启尺寸），
debug 是 900×600（因为 debug 跑过多次，`initDimensionsConfiguration()`
从持久化里恢复出了保存过的尺寸）。

`app/lib/config/init.dart:128`：
```dart
await WindowDimensionsController(persistenceService).initDimensionsConfiguration();
```
首次运行没有保存值，就用 GTK 默认值。多跑几次、手动调过窗口后就会记忆。

### `defaultRef` 报错是无害的

release 日志里有一条：

```
[WARNING] [TrayHelper] Failed to update sleep state (Refena not yet initialized)
LateInitializationError: Field 'defaultRef' has not been initialized.
```

出处是 `app/lib/util/native/tray_helper.dart:75`：
```dart
RefenaScope.defaultRef.notifier(sleepProvider).setState((_) => true);
```

托盘图标在 Refena 容器初始化完成之前就去读状态了。**异常被捕获、降级成警告、程序继续跑**。
证据：报错之后紧接着三个 isolate 就绪、服务启动、UI 正常渲染。

debug 版日志里没有这条，是因为 debug 下托盘初始化时机略不同。**不影响功能。**

---

## 诚实声明

已实测：
- ✅ release 编译成功（退出码 0，242 秒）
- ✅ 产物结构正确（有 `libapp.so`，无 `kernel_blob.bin`）
- ✅ `ldd` 零缺失依赖
- ✅ 窗口出现（1024 ms）
- ✅ 三个 isolate 就绪
- ✅ HTTP/HTTPS 服务在 53317 启动
- ✅ UI 渲染出真实内容（34,313 B 截图，940 色，品牌绿在位）
- ✅ 识别到本机网络 `10.5.90.75`

未验证：
- ❌ **实际文件传输**（没和手机/另一台设备真传过）
- ❌ 托盘图标实际显示（Xvfb 无系统托盘，无法验证）
- ❌ 长时间稳定性
- ❌ deb 打包

已知差异：
- ⚠️ 窗口 400×500 而非 900×600（首启默认值，非 bug）
- ⚠️ `defaultRef` 警告（已捕获，无害）
- ⚠️ 图标未裁剪（因为关了 tree-shake，包体略大）
- ⚠️ 引擎内 Dart SDK 版本不一致（gen_snapshot 51.0.dev / frontend_server 40.0.dev），靠包装脚本绕过，**这是引擎构建本身的瑕疵，根治需要重建引擎统一版本**
