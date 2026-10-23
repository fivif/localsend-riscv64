# LocalSend 特有的构建问题

本文只记录 **LocalSend 项目本身**在 riscv64 上遇到的问题。

引擎层面的问题（Dart SDK 版本、artifact 布局、clang shim 等）不在本文范围，
见 [flutter-riscv64-linux](https://github.com/fivif/flutter-riscv64-linux) 的 docs。

---

## 一、cargokit 缺少 riscv64 映射

### 症状

```
SEVERE: Cargokit BuildTool failed with error:
SEVERE: Exception: Unknown target platform: linux-riscv64
```

### 根因

`packages/localsend_isolates/rust_builder/cargokit/build_tool/lib/src/target.dart`
的映射表只有 `linux-x64` 与 `linux-arm64`，没有 riscv64。
`build_cmake.dart:23` 取不到 target 便抛出异常。

### 修法

见 [`../patches/0001-cargokit-riscv64.patch`](../patches/0001-cargokit-riscv64.patch)：

```dart
Target(
  rust: 'riscv64gc-unknown-linux-gnu',   // 标准 triple
  flutter: 'linux-riscv64',
),
```

同时 `buildableTargets()` 需识别 riscv64 主机：

```dart
} else if (arch.trim().startsWith('riscv64')) {
  return [Target.forRustTriple('riscv64gc-unknown-linux-gnu')!];
}
```

### 关于 triple 的选择

补丁中实际写的是 `riscv64a23-unknown-linux-gnu`，这是 **SpacemiT 定制工具链的私有 triple**。

板上的 `rustc -vV` 报 `host: riscv64a23-unknown-linux-gnu`，且
`$(rustc --print sysroot)/lib/rustlib/` 下仅此一个 triple 有 std，系统未安装 rustup。
因此在板上必须使用它。

**通用环境应改用 `riscv64gc-unknown-linux-gnu`**，见
[`../patches/0003-上游建议版.md`](../patches/0003-上游建议版.md)。

---

## 二、`-Werror` 与 ayatana 的 deprecated 标记冲突

### 症状

```
error: 'app_indicator_new' is deprecated [-Werror,-Wdeprecated-declarations]
```

### 根因

`tray_manager` 插件在 CMake 中启用了 `-Werror`，而
`libayatana-appindicator3` 将 `app_indicator_new` 标记为 deprecated。
两者相遇，警告被提升为错误。

### 修法

见 [`../patches/0002-cmake-no-error-deprecated.patch`](../patches/0002-cmake-no-error-deprecated.patch)。
在 `app/linux/CMakeLists.txt` 中，`include(flutter/generated_plugins.cmake)` **之前**
加入：

```cmake
add_compile_options(-Wno-error=deprecated-declarations)
```

位置很关键：必须在该 `include` 之前，选项才会传播到各插件子目录。

---

## 三、pub 依赖版本冲突

### 症状

```
Because flutter_test 0.0.0 from sdk depends on both test_api 0.7.15
and matcher 0.12.20, test >=1.30.0 <1.31.2 is incompatible with
flutter_test 0.0.0 from sdk.
... freezed 3.2.5 which depends on analyzer >=9.0.0 <11.0.0 ...
```

### 根因

LocalSend 的 `dev_dependencies`（`test ^1.30.0`、`freezed`、`dart_mappable_builder`）
与本 Flutter revision 所钉的 `flutter_test` 版本不兼容。

**这是版本偏移问题，与 riscv64 无关**，在 x64 上使用同一 Flutter revision 也会遇到。

### 现状

LocalSend 的生成代码已全部提交（31 个 `*.mapper.dart`、4 个 `*.freezed.dart`、
60 个 `*.g.dart`），构建过程不需要 codegen。

因此本项目在构建时临时剥离了各 `pubspec.yaml` 的 `dev_dependencies`，
并添加了 `pubspec_overrides.yaml` 放开 `dart_mappable_builder` 版本约束。

⚠️ **这两个处理未纳入本仓库的补丁集**，因为它们属于本地临时绕过，
不是 riscv64 适配的一部分。若需复现构建，需自行处理该冲突（或使用与
`flutter_test` 钉版兼容的 Flutter revision）。

---

## 四、`shader_lib` 与 `impellerc` 的相对位置

### 症状

```
error: '#include' : Included file not found.
       for header name: flutter/runtime_effect.glsl
```

### 根因

`flutter_tools/lib/src/build_system/tools/shader_compiler.dart:223`：

```dart
final String shaderLibPath = _fs.path.join(impellerc.parent.absolute.path, 'shader_lib');
```

`shader_lib` 必须与 `impellerc` **同级**，放其他位置无效。

严格来说这不属于 LocalSend 的问题，而是安装引擎产物时的常见疏漏，
记录于此以便排查。

---

## 五、接收文件的位置与 mtime

### 现象

传输完成后，用 `find -newermt` 或 `find -mmin` 找不到文件。

### 原因

LocalSend **保留文件的原始修改时间**，因此按「最近修改」搜索无效。

### 正确做法

查看应用日志中的 `Saved <filename>` 行，或按文件名搜索：

```
[INFO] [HttpServerIsolate] Saved mmexport1792505984100.jpg.
[INFO] [ReceiveController] Received all files.
```

另：默认接收目录由应用内设置决定，我们的运行环境中为 `/root`。

---

## 六、deb 依赖的正确计算方式

### 不要用 `ldd`

`ldd` 输出的是递归闭包，会得出 69 个包名，绝大部分是冗余的传递依赖。

### 应使用 `readelf -d` 的 NEEDED

```bash
for f in bundle/localsend_app bundle/lib/*.so; do
  readelf -d "$f" | grep -a NEEDED | sed 's/.*\[\(.*\)\]/\1/'
done | sort -u
```

得到 23 个直接依赖。另需手工补 3 个 `dlopen` 加载、不出现在 NEEDED 中的库：

```
libegl1
libgbm1
libsecret-1-0
```

⚠️ 中文 locale 下 `readelf` 输出为 `共享库：[libxxx.so]`，
使用 `awk '{print $5}'` 会取错字段，必须用 `sed` 提取方括号内容。
