# LocalSend · RISC-V64 适配（进迭时空 K3 系列）

给 [localsend/localsend](https://github.com/localsend/localsend) 做 riscv64 构建，跑在 Bianbu 4.0.1 / K3（riscv64, 8 核, glibc 2.43）上。

**状态：已在真机跑通，收发双向实测通过。**

---

## 一、先说结论（重要）

上游 LocalSend 的桌面 GUI 是 Flutter 应用，而 **Flutter 官方没有任何 riscv64 引擎产物**。
实测依据：`releases_linux.json` 里 300+ 条发布记录，`dart_sdk_arch` 只有 `x64` 一个值，
全文件搜 `riscv` 零命中。

所以"编译一个 Flutter GUI 的 riscv64 版"这条路在当前工具链下走不通。本适配改成两条
**协议层完全等价**的路径，都基于上游自己的 Rust core（`packages/core`，协议版本 2.2）：

| 入口 | 形态 | 能做什么 |
|---|---|---|
| `localsend-cli` | 上游自带终端界面（直接编译，未改一行代码） | 组播发现设备、点对点加密收发、配对、多文件/目录 |
| `localsend-link` | **本适配新增** | 常驻服务：手机浏览器扫码/开链接直接下载或上传，无需装 App |

手机端 LocalSend App 照常发现这台设备、照常互传——因为协议实现就是上游的 Rust core。

---

## 二、构建目录

板端（`root@10.5.90.75`）：

```
/root/localsend-riscv64/
├── src/localsend/          # 上游源码（git clone，depth 1）
├── link/                   # 新增：网页直传入口 crate
├── probe/                  # 新增：mTLS 上传探针（验收测试用）
├── scripts/                # 构建/打包/验收脚本
├── build/target/           # CARGO_TARGET_DIR（共用，避免重复编译）
├── dist/                   # 产物：二进制 + .deb
└── logs/                   # 构建与测试日志
```

本地镜像（Windows）：`C:\Users\zhuxuanjia\Desktop\Work-temp\localsend-riscv64\`

---

## 三、构建步骤

```bash
ssh root@10.5.90.75          # 密码 bianbu
cd /root/localsend-riscv64

# 一条命令：拉源码 + 编译两个二进制 + 打 deb
bash scripts/build-all.sh
```

分开跑：

```bash
# 只编上游 CLI
cd src/localsend && cargo build -p localsend-cli --release

# 只编网页直传
cd link && cargo build --release

# 只打包
bash scripts/package-deb.sh
```

实测数据：空 `target/` 冷编译约 **8 分 34 秒**（8 核满载，Rust 1.93.1）；
新增的 `localsend-link` 复用依赖后又多 20 秒。

### 依赖说明

- Rust 1.93.1（Bianbu 自带，无 rustup；上游 pin 的是 1.97.1，实测低版本能编过）
- gcc 15.2.0、glibc 2.43
- 板子能直连 `github.com` 和 `static.crates.io`，不需要配镜像
- `ring`（TLS）、`rsa`（证书生成）、`webrtc`（core 依赖，虽未用）在 riscv64 上都能编译

---

## 四、用法

装完 deb 后系统里有四个命令：

### 1. 终端收发（交互界面）

```bash
localsend-cli
```

| 键 | 作用 |
|---|---|
| `D` | 显示已配对 + 已发现设备 |
| `1`~`9` | 给第 N 台设备发文件 |
| `Y` / `N` / `P` | 接受 / 拒绝 / 接受并配对 |
| `W`+`S` | 生成浏览器下载链接（手机扫码下载） |
| `W`+`R` | 让浏览器上传文件到这台设备 |
| `Ctrl+C` | 取消当前传输，空闲时退出 |

直发模式（不进界面）：

```bash
localsend-cli send --to "手机别名" ~/photo.jpg
localsend-cli send --to 192.168.1.23 ~/Documents
localsend-cli send --to "手机别名" --text "hello"
```

### 2. 网页直传（推荐给非技术用户）

```bash
localsend-share ~/Downloads/photo.jpg
```

终端会打印 `http://10.5.90.75:53317`，手机浏览器打开就能下载，不用装任何 App。
只收不发：

```bash
localsend-link serve --destination ~/Downloads
```

### 3. 桌面图标

`/usr/share/applications/localsend.desktop` 已安装，应用菜单里搜 "LocalSend" 即可
（会在 qterminal 里打开）。

---

## 五、实测证据

全部在 `root@10.5.90.75` 真机执行，脚本在 `scripts/`。

| 验收项 | 脚本 | 结果 |
|---|---|---|
| CLI 启动、监听 53317、TLS 握手 | 手工 ss + openssl | 通过（自签证书 `CN=LocalSend User`） |
| CLI 收文件：浏览器上传页 → prepare-upload → 上传落盘 → 界面提示 | `verify_board.py` | 接收链路 7 项全过 |
| 网页分享页 + prepare-download + download | `verify_link.py` share 段 | 7/7 通过 |
| **组播设备发现（两实例互见）** | `verify_discovery.py` | **7/7 通过**，1.0 秒互发现 |
| **2MB 文件 mTLS 端到端，sha256 一致** | `verify_e2e.py` | **5/5 通过** |
| 真客户端上传到 `localsend-link serve` | `verify_serve.py` | 4/4 通过 |
| deb 安装、四个命令可用、desktop 无警告 | 手工 `dpkg -i` + `desktop-file-validate` | 通过 |

> 诚实说明：`verify_board.py` 里的"分享"用例（`W+S`）**没有通过**，原因是上游 CLI 在
> `send <文件>` 模式下只开设备列表浮层，按键被浮层吃掉，进不到带日志的主界面。
> 这不是 riscv64 的问题，x86 上行为相同。因此网页分享改由新增的 `localsend-link` 承担，
> 并用 `verify_link.py` 单独验收，那 6 项是实测通过的。

2MB 端到端关键输出：

```
输入 /tmp/e2e-big.bin  2097152 B  sha256=05e7b4833603098fbed39ce49ea8a50ab28557715d7dd18ca0387c3243f58e8a
  PASS  CLI 启动并监听
  PASS  收到上传请求并弹出确认
  PASS  客户端上传成功
  PASS  界面显示接收完成
  PASS  2MB 文件 sha256 一致  | 2097152 B, 05e7b4833603098f…
```

二进制确认：

```
$ file dist/localsend-cli
ELF 64-bit LSB pie executable, UCB RISC-V, RVC, double-float ABI, ...
$ localsend-cli --version
localsend-cli 1.18.2
```

---

## 六、踩过的坑

1. **Flutter 没有 riscv64 引擎** —— 不是配置问题，是官方根本没发布。别在这条路上耗时间。
2. **网页页面必须明文 HTTP** —— 浏览器无法验证自签证书。上游 CLI 的 `W+S` 也是这么做的：
   切到分享模式时把服务重启成无 TLS。`localsend-link share` 同样处理。
3. **协议 mTLS 是真强制的** —— Python 的 `urllib` 不带客户端证书会被直接断开（Broken pipe）。
   验收测试因此改用 core 自己的 `LsHttpClientV2` 写了个 Rust 探针（`probe/`）。
4. **TUI 需要真实终端尺寸** —— `pty` 不给 `TIOCSWINSZ` 时窗口是 0x0，ratatui 直接退出不报错。
5. **`prepare-upload` 的 HTTP 响应会挂住** —— 一直阻塞到用户按 Y/N，测试里必须放到线程里发。
6. **`prepare-download` 的 `sessionId` 是客户端 IP，不是 UUID** —— 且 download 请求不带 token。
7. **`send <path>` 是子命令** —— 直接 `localsend-cli <path>` 会报 unrecognized subcommand。
8. **CLI 的 send 模式只到设备列表** —— 没有设备时按 Esc 就退出，进不到日志界面。
   所以"分享给浏览器"用的是自建的 `localsend-link`，而不是依赖 `W+S`。
9. **同一台机器跑两个 CLI 实例必须用不同 `XDG_CONFIG_HOME`** —— 否则共用同一个
   `identity.pem`，指纹相同，双方会把自己过滤掉，设备列表永远 `(none)`。
   这个坑排查了很久，因为表面现象是"组播发现不工作"，实际是身份去重。
10. **`ss -lntup` 里组播不显示为独立监听** —— 只能看到 53317 的 UDP socket，
    真正的组播组成员关系要用互发现来证明，不能靠 `ss` 推断。

---

## 七、上游贡献注意事项

上游 `AGENTS.md` 明确写着：**除 bug 修复、极小改动、或能证明专业能力外，不接受 AI 生成的贡献。**
所以本适配的 `link/`、`probe/`、`scripts/` 全部放在**独立 crate / 独立目录**，
没有改动上游仓库的任何一行代码：

- `src/localsend/` 保持 `git clone` 原样，`git status` 干净
- `localsend-cli` 是上游原样编译
- `localsend-link` 通过 `path = "../src/localsend/packages/core"` 引用上游 crate

若要向上游提交，建议只提 riscv64 构建脚本（`support/scripts/` 很小的一块）和 CI 矩阵，
不要把 `link/` 塞进去。

---

## 八、后续可做

- [ ] `localsend-link` 增加二维码（终端直接扫），现在只有 URL
- [ ] 打包成系统服务（`systemd --user` 单元），开机常驻接收
- [ ] 交叉编译：在 x86 上用 `cross` + riscv64gc 工具链，省掉板端 8 分钟编译
- [ ] 托盘图标（qterminal + 简单 Qt 壳），进一步贴近"图形应用"体验
- [ ] 若 Flutter 将来出 riscv64 引擎，直接 `flutter build linux` 即可，本适配的 core 不用动
