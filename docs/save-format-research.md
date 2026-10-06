# 忍者外传 黑之章（Xbox，TitleID 5443000D）存档研究

验证样本：30 个真实存档，下面的结论全部对 30/30 成立（标注"推测"的除外）。

## 1. 目录结构
```
UDATA\5443000d\
  TitleMeta.xbx / TitleImage.xbx / SaveImage.xbx      ← 游戏级文件
  <12位十六进制ID>\                                   ← 每个存档一个文件夹
      SaveMeta.xbx    UTF-16LE(带BOM)：Name=<存档名>\r\nNoCopy=1
      save000.dat     固定 95,400 字节（0x174A8），加密
```
`save000.dat` 的文件名来自游戏里的 `save%03d.dat`，实际只用 000。

## 2. 文件夹命名逻辑（核心）
文件夹名**不是随机的，也不是时间戳**，而是 XDK 的 `XCreateSaveGame` 对"存档名"做哈希得到的：

```
h = 0
for ch in 存档名(UTF-16 每个字符):
    h = (h * 0x10000 + ch) mod (2^48 - 59)      # 模数 0xFFFFFFFFFFC5
文件夹名 = h 的 12 位大写十六进制
```
- 算法来自 XBE 里 0x328ccb 的函数，我反汇编后用 Python 复现，30 个文件夹全部吻合。
- 存档名与 SaveMeta.xbx 的 `Name=` 是同一个字符串。所以**同一槽位、章节、时间相同才会得到同一个文件夹名**；每次存档时间变了，文件夹名就变（游戏会删旧建新）。
- 存档名模板（取自 XBE 字符串表）：
  - 章节存档：`%d. CHAPTER %d %s`，例如 `18. CHAPTER 12 008:34`
  - Mission 模式：`%d. MISSION %s`
  - `%s` 为 `%03d:%02d`，即 **小时(3位):分钟(2位)** 的游玩时间。
- 反过来也成立：知道（槽位, 章节, 时间）就能算出文件夹名，所以软件改名/整理时必须同时改 SaveMeta 的 Name，否则哈希对不上。

## 3. 存档里能读到什么
| 信息 | 来源 | 说明 |
|---|---|---|
| 槽位 | SaveMeta Name 开头的数字 | 1–30 |
| 章节号 | Name 里的 `CHAPTER n`；解密数据 0x16842（0 起算）可交叉验证 | 1–16 |
| 游玩时间 | Name 里的 HHH:MM；帧数 u32，÷60 得秒（位置见下方"注意"） | 精确到秒 |
| 难度 | 解密数据 0x16840（u8） | 0 Ninja Dog / 1 Normal / 2 Hard / 3 Very Hard / 4 Master Ninja（已由实机确认） |
| 模式 | Name 是 CHAPTER 还是 MISSION | |
| Karma | 解密数据 0x1664B（u32，结构体 +0x16620） | 与读档界面 KARMA 一致（实机确认） |
| 存档点 | 解密数据 0x167D9（u8，结构体 +0x167AE），换算见第 6 节 | Mission 存档为 0x26 起的 PHASE 编号 |

> **注意（更正）**：本节里写的 0x16653 / 0x16840 / 0x16842 / 0x16849 都是**原始解密明文**的偏移。save000.dat 解密后其实是一段区间编码（range coder）压缩流，不是直接的结构体；压缩流之后是游戏缓冲区里的残留数据，旧版本读到的就是残留里的未压缩原数据，所以"碰巧"读得到值。正确读法：解密 → 区间解码 → 跳过 0x2A 字节头 → 结构体 `+0x16628` 处的 u32 是帧数（解码后偏移 0x16652，即比旧偏移少 1）。难度/章节/存档点的旧偏移也是同样的关系（抽查 8 个存档：解码后偏移 −1 处的值与旧读法相同）。
> 格式和编解码见 [system-dat-research.md](system-dat-research.md)；本仓库的新功能用解码后的值，旧的显示逻辑暂时保留，并提供两者是否一致的检查（本地 30 个存档全部一致）。

## 4. save000.dat 加密（来自 feudalnate/NinjaCrypt，已用 Python 复现并全部解密成功）
```
0x00  20字节  HMAC-SHA1 签名（与 XboxHDKey + 游戏签名密钥绑定，换主机要重签）
0x14   4字节  seed（小端 u32）
0x18  95,376字节 数据
解密：MT19937变体(seed) → 先取 56 字节作 Blowfish 密钥 → 数据逐个 u32 与 MT 输出异或 → Blowfish(16轮) 按 8 字节块解密（小端 u32）
成功标志：解密数据最后 6 字节 = 94 45 8E D2 8A 4F
解密后的数据本身是区间编码压缩流（byte0 = 频率表格式），后面跟缓冲区残留；上面那 6 字节在残留的最末尾。
```
**读取存档信息不需要任何密钥**，只有重新加密/重签才需要 XboxHDKey。

## 5. 没有解决的部分
- **章节名字**：章节标题不在存档里，软件不显示（标题文本在 spr.afs #363 的 0x0E 组，需要时可加）。
- 槽位 1–4 的 CHAPTER 15 存档不同难度、时间不递增，显然是手动整理的存档，不影响解析。
- 旧版本当成"存档点 ID"的 0x16849 其实不是存档点（含义未知），已弃用。

## 6. 存档点名字（反汇编 default.xbe，NGB USA）
地址均为 default.xbe 的虚拟地址；"结构体"指解码后跳过 0x2A 头的存档结构体，对应旧读法的解密明文偏移 = 结构体偏移 + 0x2B。
- **0x179db0**：读档界面从存档结构体填一条摘要记录：`+0x00` 帧数(+0x16628)、`+0x08` Karma(+0x16620)、`+0x18` 存档点编号(+0x167AE)、`+0x1a` 章节(+0x16817)、`+0x1d` 难度(+0x16815)、`+0x1e` 赛事序号(+0x16812)；`+0x16` = `0x229c10(章节, 存档点编号, 类别字节 +0x1681A)`。
- **0x228c7a**（读档界面 SAVE POINT 行）：`+0x18 >= 0x26` 时显示 PHASE 文字表 `0x43b4d0[编号 − 0x26]`（PHASE 1–4 COMPLETE、"--- PHASE 5 ---"、PHASE 5–8 COMPLETE，即 Mission/Eternal Legend）；否则显示消息 `0x120000 | +0x16`。
- **0x229c10**：编号 → 消息下标。0x32 → 0x35；章节 0xFE → 0x27；大多数编号查一张 50 项的表；编号 1、2、4–8、12、13、34、35 按章节在两个同名消息里二选一（例如第 8 章用 Tairon 那组）；类别字节不是 0/1 时一律为 0x31 Master Ninja Tournament。代码里的 `save_point_index()` 是逐条移植。
- **消息文本**：`0x1e6ae0` 查消息，组号 ≥ 0x0B 的组在运行时从 `MESSTR` 文件载入；存档点是 0x12 组，在 spr.afs 第 363 个文件里（54 条，英/日两种语言）。
- 验证：本地 30 个存档的名字与关卡吻合，旧偏移读法与正规解码结果全部一致；Mission 存档编号 0x26 = PHASE 1 COMPLETE 与实机截图一致。


## 5.5 HD Key 签名（已用 30 个真实存档验证）
文件头 20 字节是 HMAC-SHA1 签名，覆盖 0x14 之后的全部内容（加密后的字节，所以重签不需要解密）：
```
sigkey = HMAC_SHA1(5C0733AE0401F7E8BA7993FDCD2F1FE0, 游戏签名密钥)[:16]     游戏签名密钥 = FC3376488B3E5F00F65A6BDA9209CFE8
签名   = HMAC_SHA1(HDKey, HMAC_SHA1(sigkey, 文件[0x14:]))
```
- 你现有的 30 个存档全部匹配"忍外黑密钥 + Xbox 360 旧KV 的 HD key"。
- 把存档重签成 xemu 的 key 再签回 360 旧KV，结果与原文件逐字节一致。
- 存档里没有其它与主机绑定的数据（不像 DOA 的 ups.dat 还绑定 MAC）。

## 5.6 TDATA 系统存档 system.dat
位置 `TDATA\5443000D\system.dat`，固定 0x550（1,360）字节，签名方式与 save000.dat 完全相同（偏移 0 的 20 字节 HMAC，覆盖 0x14 之后，同一游戏签名密钥，NoRoam）。重签只需 HD Key，软件会自动处理。
来源：[feudalnate/Original-Xbox-Gamesave-Resigners](https://github.com/feudalnate/Original-Xbox-Gamesave-Resigners/tree/master/Ninja-Gaiden-Black)。
**system.dat 的内容（读档列表的每档游玩时间、显示顺序）已逆向，详见 [system-dat-research.md](system-dat-research.md)。**

## 6. 配套工具
`ngb_save_info.py`：纯 Python、无需安装依赖。
```
python ngb_save_info.py "<...>\5443000d" --csv saves.csv
```
输出槽位、文件夹、章节、时间、精确游玩时间、难度，并校验文件夹哈希是否与存档名一致。

`ngb_save_manager.py`（图形界面）在此基础上还有：移动槽位、按 HD Key 重签、显示每个存档的签名属于哪个 HD Key、更新 system.dat（游玩时间表/列表顺序）。

`ngb_system_dat.py`：system.dat 的编解码与编辑（命令行，GUI 复用），见 [system-dat-research.md](system-dat-research.md)。

## 来源
- [feudalnate/NinjaCrypt](https://github.com/feudalnate/NinjaCrypt)（加密算法、存档尺寸）
- [xboxdevwiki: Xbox Savegame System](https://xboxdevwiki.net/Xbox_Savegame_System)（目录布局、SaveMeta/TitleMeta 格式）
- 文件夹哈希算法为本次从你提供的 XBE 反汇编得出
