# deb 打包

## 产物

| 包 | 大小 | 内容 |
|---|---|---|
| `localsend-gui-riscv64_1.18.2_riscv64.deb` | 21,480,920 B（20.5 MB） | 完整 GUI |
| `localsend-riscv64_1.18.2_riscv64.deb` | 4,802,220 B（4.6 MB） | CLI + 网页直传 |

## 包结构

```
/opt/localsend-gui/                    67 MB
├── localsend_app                      27,424 B   ELF64 RISC-V
├── lib/
│   ├── libapp.so                      15,729,544 B  AOT 机器码
│   ├── libflutter_linux_gtk.so        13,996,360 B  自建引擎
│   ├── librust_lib_localsend_app.so   24,133,064 B  Rust core
│   └── lib*_plugin.so × 15
└── data/
    ├── icudtl.dat                     10,824,432 B
    └── flutter_assets/

/usr/local/bin/localsend-gui
/usr/share/applications/localsend-gui.desktop
/usr/share/icons/hicolor/256x256/apps/localsend-gui.png
```

## 依赖是怎么算出来的

**不要用 `ldd` 的完整输出**，那是递归闭包，会得出 69 个包，全是冗余。

用 `readelf -d` 的 `NEEDED`，那才是真正的直接依赖：

```bash
for f in bundle/localsend_app bundle/lib/*.so; do
  readelf -d "$f" | grep -a NEEDED | sed 's/.*\[\(.*\)\]/\1/'
done | sort -u
```

⚠️ 中文 locale 下 `readelf` 输出是 `共享库：[libxxx.so]`，
用 `awk '{print $5}'` 会取错字段，必须用 `sed` 正则提取方括号内容。

拿到库名后映射包名：

```bash
dpkg -S "*/libgtk-3.so.0" | cut -d: -f1     # → libgtk-3-0t64
```

结果 23 个。另外三个是 dlopen 加载的、不出现在 NEEDED 里，要手工补：
`libegl1`, `libgbm1`, `libsecret-1-0`。

## 安装测试（真实执行）

```
dpkg -i localsend-gui-riscv64_1.18.2_riscv64.deb   → 退出码 0
dpkg -l | grep localsend
  ii  localsend-gui-riscv64  1.18.2  riscv64      ← 新增
  ii  localsend-riscv64      1.18.2  riscv64      ← 原有，共存无冲突
ldd /opt/localsend-gui/localsend_app | grep -c "not found"   → 0
dpkg -V localsend-gui-riscv64                                → 无输出
desktop-file-validate .../localsend-gui.desktop               → 无输出
```

从安装路径启动：

```
/usr/local/bin/localsend-gui
  → 窗口 1026 ms 出现
  → DiscoveryIsolate / HttpUploadIsolate / HttpServerIsolate 就绪
  → Server started. (Port: 53317, HTTPS only)
  → Network state: [10.5.90.75]
```

## 踩到的一个小问题

第一次 `desktop-file-validate` 报：

```
hint: value "Network;FileTransfer;Utility;" for key "Categories" contains
      more than one main category; application might appear more than once
```

`Network` 和 `Utility` 都是主类别，应用会在菜单里出现两次。
改成 `Categories=Network;FileTransfer;` 后校验干净。

## 打回源码树

`build-deb.sh` 需要先有一次成功的 release 构建。它做的事：

1. 把 `bundle/` 拷到 `packaging/gui/opt/localsend-gui/`
2. `strip --strip-unneeded` 掉插件的调试符号
3. 写 `DEBIAN/control`（依赖从 `readelf` 现算）
4. `dpkg-deb --build --root-owner-group`

`postinst` 只做两件事：刷新图标缓存、刷新 desktop 数据库，都允许失败。
