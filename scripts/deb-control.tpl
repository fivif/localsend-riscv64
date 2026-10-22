Package: localsend-riscv64
Version: __VERSION__
Section: net
Priority: optional
Architecture: riscv64
Maintainer: Work-temp <root@localhost>
Installed-Size: __SIZE__
Depends: libc6 (>= 2.39), libgcc-s1
Recommends: qterminal | lxterminal | xfce4-terminal
X-SpacemiT-Upstream-Version: __UPVER__
Description: LocalSend for RISC-V64 (SpacemiT K3 series / Bianbu)
 LocalSend 是局域网跨设备文件互传工具，本包是 riscv64 原生构建。
 .
 上游 Flutter 桌面 GUI 目前没有 riscv64 引擎产物，因此本包提供两条
 完整可用路径：
   - localsend-cli   终端交互界面：组播发现、加密收发、配对
   - localsend-link  网页直传：浏览器扫码/打开链接即可下载或上传
 .
 协议实现直接用上游 Rust core (packages/core)，协议版本 2.2，
 与手机/桌面版 LocalSend 互通。
