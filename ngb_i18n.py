# -*- coding: utf-8 -*-
"""
ngb_i18n.py - tiny UI translation layer. Source strings are Chinese; t(zh) returns the English text when the
language is "en". Language: NGB_LANG env var, else ngb_lang.json next to the script, else the system UI language.
"""
import os, sys, json, locale

LANG_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else os.getcwd(), "ngb_lang.json")
LANGS = ("zh", "en")

def _detect():
    env = os.environ.get("NGB_LANG", "").lower()
    if env in LANGS: return env
    try:
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            v = json.load(f).get("lang")
        if v in LANGS: return v
    except Exception: pass
    try:
        loc = (locale.getdefaultlocale()[0] or "").lower()
    except Exception: loc = ""
    return "zh" if loc.startswith("zh") or "chinese" in loc else "en"

LANG = _detect()

def set_lang(lang, persist=True):
    global LANG
    if lang not in LANGS: return
    LANG = lang
    if persist:
        try:
            with open(LANG_FILE, "w", encoding="utf-8") as f: json.dump({"lang": lang}, f)
        except Exception: pass

def t(zh):
    return EN.get(zh, zh) if LANG == "en" else zh

EN = {
    # --- save manager: errors / results ---
    "存档名格式不认识: %r": "Unrecognised save name format: %r",
    "两个存档会得到相同的文件夹名": "Two saves would end up with the same folder name",
    "目标文件夹已存在: ": "Target folder already exists: ",
    "改完后校验失败: ": "Verification failed after the change: ",
    "HD key 需要 32 个十六进制字符": "An HD key needs 32 hex characters",
    "输出文件夹不为空: ": "Output folder is not empty: ",
    "大小不对，已原样复制": "Wrong size, copied unchanged",
    "验证失败": "Verification failed",
    "system.dat 大小不对(%d)，未处理": "system.dat has the wrong size (%d), skipped",
    "目标已存在，已跳过": "Target already exists, skipped",
    "SetClipboardData 失败": "SetClipboardData failed",
    "无法打开剪贴板": "Cannot open the clipboard",
    # --- columns ---
    "槽位": "Slot", "模式": "Mode", "章节": "Chapter", "存档时间 HHH:MM": "Save time HHH:MM",
    "精确游玩时间": "Exact play time", "难度": "Difficulty", "存档点ID(原始)": "Save point ID (raw)",
    "文件修改时间": "Modified", "文件夹名": "Folder", "签名属于(HD Key)": "Signed by (HD Key)",
    "校验": "Check", "备注": "Note",
    # --- main window ---
    "忍者外传 黑之章 存档管理器 (Xbox / 5443000D)": "Ninja Gaiden Black Save Manager (Xbox / 5443000D)",
    "选择存档文件夹…": "Choose save folder…", "刷新": "Refresh", "导出 CSV…": "Export CSV…",
    "删除": "Delete", "删除失败": "Delete failed", "删除所选 (Del)": "Delete selected (Del)", "删除所选存档（%d 个）": "Delete selected saves (%d)",
    "确定永久删除选中的 %d 个存档文件夹吗？\n槽位: %s\n\n此操作不可撤销，建议先“复制所选存档到…”备份。": "Permanently delete the %d selected save folders?\nSlots: %s\n\nThis cannot be undone. Consider backing up with \"Copy selected to…\" first.",
    "编辑备注": "Edit note", "移动到槽位…": "Move to slot…", "HD Key 重签…": "Re-sign with HD Key…",
    "system.dat 重签…": "Re-sign system.dat…", "system.dat 更新…": "Update system.dat…",
    "打开所选存档文件夹": "Open selected save folder", "筛选:": "Filter:", "（未选择）": "(none selected)",
    "全选 (Ctrl+A)": "Select all (Ctrl+A)", "复制所选到…": "Copy selected to…",
    "复制所选到剪贴板（资源管理器 Ctrl+V 粘贴）": "Copy selected to clipboard (paste in Explorer with Ctrl+V)",
    "Ctrl/Shift 多选": "Ctrl/Shift for multi-select",
    "选择 UDATA\\5443000d 文件夹（或其上级）": "Choose the UDATA\\5443000d folder (or its parent)",
    "未找到存档": "No saves found",
    "这个文件夹里没有找到含 SaveMeta.xbx 的存档子文件夹。\n请选择 UDATA\\5443000d。":
        "No save subfolders containing SaveMeta.xbx were found in this folder.\nPlease choose UDATA\\5443000d.",
    "(读取失败: %s)": "(read failed: %s)", "未识别": "unknown",
    "解密失败": "Decrypt failed", "正常": "OK", "名称≠哈希": "Name≠hash",
    "共 %d 个存档，显示 %d 个%s。点列标题排序，双击一行打开该存档文件夹，右键更多操作。":
        "%d saves, %d shown%s. Click a column header to sort, double-click a row to open its folder, right-click for more.",
    "；%d 个文件夹名与存档名哈希不一致（红色）": "; %d folder names do not match the save-name hash (red)",
    "已选 %d 个存档，槽位: %s\n可以右键或用上方按钮：复制所选到…、复制到剪贴板、HD Key 重签（重签会作用于全部选中的）。":
        "%d saves selected, slots: %s\nUse right-click or the buttons above: copy selected to…, copy to clipboard, HD Key re-sign (applies to all selected).",
    "解码值 %d 帧，旧读法(原始明文 0x16653) %d 帧：%s": "decoded %d frames, old reading (raw plaintext 0x16653) %d frames: %s",
    "一致": "match", "不一致": "mismatch", "无法检查 (%s)": "cannot check (%s)",
    "签名属于: %s\n存档名(SaveMeta Name): %s\n文件夹: %s\n按命名规则由存档名算出的文件夹名: %s  →  %s\n章节(存档名): %s    章节(存档数据): %s\n游玩帧数检查: %s\n路径: %s":
        "Signed by: %s\nSave name (SaveMeta Name): %s\nFolder: %s\nFolder name computed from the save name: %s  →  %s\nChapter (from name): %s    Chapter (from save data): %s\nPlay-frames check: %s\nPath: %s",
    "备注 - ": "Note - ", "保存": "Save",
    # --- move slot ---
    "移动槽位": "Move slot", "移动槽位一次只能选一个存档。": "Select only one save to move.",
    "请先选中一个存档。": "Select a save first.", "移动到槽位": "Move to slot",
    "当前槽位 %s（%s）\n移到槽位号:": "Current slot %s (%s)\nMove to slot number:",
    "请输入数字。": "Please enter a number.",
    "请输入不同于当前、且大于 0 的槽位号。": "Enter a slot number greater than 0 and different from the current one.",
    "你现有存档最大槽位是 30，游戏是否支持超过 30 的槽位还没验证。\n仍要继续吗？":
        "Your highest existing slot is 30; whether the game supports slots above 30 is unverified.\nContinue anyway?",
    "槽位已被占用": "Slot occupied",
    "槽位 %d 已有存档（%s）。\n\n是 = 与它交换位置\n否 = 取消": "Slot %d already has a save (%s).\n\nYes = swap places with it\nNo = cancel",
    "备份失败": "Backup failed", "没有备份就不会修改任何文件。\n%s": "No files are modified without a backup.\n%s",
    "移动失败": "Move failed", "完成": "Done",
    "已移动到槽位 %d%s。\n备份在:\n%s\n\n提示：读档列表里的游玩时间和顺序存在 TDATA\\5443000d\\system.dat 里，不在存档里。移动槽位后建议顺带更新它（推荐“按整套 UDATA 同步”）。\n现在打开 system.dat 更新窗口吗？":
        "Moved to slot %d%s.\nBackup in:\n%s\n\nNote: the play times and order in the load-game list are stored in TDATA\\5443000d\\system.dat, not in the saves. After moving slots you should update it too (recommended: \"Sync from the whole UDATA\").\nOpen the system.dat update window now?",
    "（并与原占用者交换）": " (swapped with the previous occupant)", "确定": "OK",
    # --- re-sign saves ---
    "重签": "Re-sign", "请先选择存档文件夹。": "Choose a save folder first.", "HD Key 重签": "Re-sign with HD Key",
    "把存档重新签名为目标主机的 HD Key（原存档不会被修改，结果写到新文件夹）":
        "Re-sign the saves with the target console's HD Key (originals are not modified; the result goes to a new folder)",
    "目标 HD Key:": "Target HD Key:", "自定义…": "Custom…",
    "只重签选中的存档（%d 个）": "Re-sign selected saves only (%d)", "重签全部 %d 个存档": "Re-sign all %d saves",
    "可在 hd_keys.json 里增删常用 HD Key。": "Add or remove common HD keys in hd_keys.json.",
    "没有选中的存档。": "No saves selected.", "重签失败": "Re-sign failed",
    "已重签": "re-signed", "失败 ": "failed ", "\nTDATA system.dat 失败: %s": "\nTDATA system.dat failed: %s",
    "\n（未找到 TDATA\\5443000d\\system.dat，仅重签 UDATA）": "\n(TDATA\\5443000d\\system.dat not found; only UDATA re-signed)",
    "重签完成": "Re-sign complete",
    "成功 %d / %d 个。\n输出文件夹（UDATA / TDATA 子文件夹可直接拷到目标主机）:\n%s%s%s":
        "%d / %d succeeded.\nOutput folder (the UDATA / TDATA subfolders can be copied straight to the target console):\n%s%s%s",
    "\n\n有问题的: ": "\n\nProblems: ", "开始重签": "Start re-signing",
    # --- re-sign system.dat ---
    "TDATA system.dat 重签": "Re-sign TDATA system.dat",
    "读取 TDATA\\5443000d\\system.dat（1,360 字节），重签为目标 HD Key（原文件不会被修改）":
        "Read TDATA\\5443000d\\system.dat (1,360 bytes) and re-sign it with the target HD Key (the original is not modified)",
    "请选择 system.dat。": "Choose a system.dat.", "读取失败: %s": "Read failed: %s",
    "大小 %d 字节，不是 system.dat（应为 %d）。": "Size is %d bytes, not a system.dat (should be %d).",
    "大小正常。当前签名属于: %s": "Size OK. Currently signed by: %s",
    "未识别（不在 hd_keys.json 里）": "unknown (not in hd_keys.json)",
    "选择 system.dat": "Choose system.dat", "所有文件": "All files", "浏览…": "Browse…",
    "请先选择 system.dat。": "Choose a system.dat first.",
    "已重签，输出（拷到目标主机的 TDATA\\5443000d）:\n": "Re-signed. Output (copy to TDATA\\5443000d on the target console):\n",
    # --- update system.dat ---
    "更新 system.dat（读档列表的游玩时间 / 顺序）": "Update system.dat (load-game list play times / order)",
    "底本必须是从 xemu / 360 当前拷出来的 system.dat（总时间、解锁、设置会原样保留）。原文件不会被修改，结果写到 resigned/<key>_<时间>/TDATA/5443000d/system.dat。":
        "The base must be a system.dat copied from the current xemu / 360 (total time, unlocks and settings are kept as is). The original is not modified; the result goes to resigned/<key>_<time>/TDATA/5443000d/system.dat.",
    "底本 system.dat:": "Base system.dat:",
    "更新单个档位（选一个存档文件夹）": "Update one slot (pick one save folder)",
    "按整套 UDATA 同步（存在的写真实帧数，不存在的写 0）": "Sync from the whole UDATA (real frames for existing slots, 0 for missing ones)",
    "重置顺序（count=30，0..29）": "Reset order (count=30, 0..29)",
    "选择文件夹": "Choose folder", "存档文件夹:": "Save folder:", "5443000d 文件夹:": "5443000d folder:",
    "点“预览”查看修改前后对比（不写文件）；点“写出”生成新的 system.dat。":
        "Click \"Preview\" to see a before/after comparison (nothing is written); click \"Write\" to generate a new system.dat.",
    "请先选择底本 system.dat。": "Choose the base system.dat first.",
    "请先选择%s。": "Choose the %s first.", "存档文件夹": "save folder", "5443000d 文件夹": "5443000d folder",
    "出错: %s": "Error: %s", "system.dat 更新失败": "system.dat update failed",
    "\n\n已写出并校验通过（重新解码一致、签名正确、其余字节未变）:\n":
        "\n\nWritten and verified (re-decodes identically, signature correct, other bytes unchanged):\n",
    "system.dat 已更新": "system.dat updated",
    "输出（拷到目标主机的 TDATA\\5443000d）:\n": "Output (copy to TDATA\\5443000d on the target console):\n",
    "预览": "Preview", "写出": "Write",
    # --- open / copy ---
    "打开文件夹": "Open folder", "请先在列表里选中一个存档。": "Select a save in the list first.", "打开失败": "Open failed",
    "复制": "Copy", "请先选中存档（可 Ctrl/Shift 多选，或点“全选”）。": "Select saves first (Ctrl/Shift for multi-select, or click \"Select all\").",
    "选择复制到哪个文件夹（会在里面放入 %d 个存档文件夹）": "Choose the destination folder (%d save folders will be placed in it)",
    "同时复制标题文件（TitleMeta/TitleImage/SaveImage），并按 UDATA 结构放进名为 %s 的子文件夹吗？\n\n是 = 目标里新建 %s 子文件夹\n否 = 只把 %d 个存档文件夹直接放进所选文件夹":
        "Also copy the title files (TitleMeta/TitleImage/SaveImage) and place everything in a subfolder named %s, following the UDATA layout?\n\nYes = create a %s subfolder in the destination\nNo = put only the %d save folders directly into the chosen folder",
    "复制失败": "Copy failed", "复制完成": "Copy complete",
    "已复制 %d / %d 个存档（按槽位顺序，修改时间依次递增）。\n目标: %s%s":
        "Copied %d / %d saves (in slot order, modification times increasing).\nTarget: %s%s",
    "\n\n跳过: ": "\n\nSkipped: ", "非 Windows 系统，已把 %d 个路径复制成文本。": "Not Windows: copied %d paths as text.",
    "已复制到剪贴板": "Copied to clipboard",
    "已复制 %d 个存档文件夹。\n在资源管理器目标位置按 Ctrl+V 粘贴即可。": "Copied %d save folders.\nPaste in Explorer at the destination with Ctrl+V.",
    "打开存档文件夹（%s）": "Open save folder (%s)", "复制完整路径": "Copy full path", "复制文件夹名": "Copy folder name",
    "复制所选存档到…（%d 个）": "Copy selected saves to… (%d)", "复制所选到剪贴板（%d 个）": "Copy selected to clipboard (%d)",
    "已导出": "Exported",
    # --- system.dat module ---
    "system.dat 大小不对(%d)，应为 %d": "system.dat has the wrong size (%d), expected %d",
    "解密后尾部标记不对：不是本游戏的 system.dat，或文件已损坏": "Wrong tail marker after decryption: not this game's system.dat, or the file is corrupt",
    "解码后长度 0x%X，应为 0x%X": "Decoded length 0x%X, expected 0x%X",
    "解码后的头部不对": "Wrong header after decoding",
    "结构魔数不是 0x%08X": "Structure magic is not 0x%08X",
    "顺序表内容不合法 (count=%d)": "Invalid order table (count=%d)",
    "save000.dat 大小不对(%d)": "save000.dat has the wrong size (%d)",
    "save000.dat 解密失败": "save000.dat decryption failed",
    "save000.dat 解码后太短(0x%X)": "save000.dat too short after decoding (0x%X)",
    "槽位  文件夹         解码后帧数  旧读法帧数  结果": "Slot  Folder         Decoded frames  Old-read frames  Result",
    "%s: 读取失败 (%s)": "%s: read failed (%s)",
    "共 %d 个存档，%d 个不一致，%d 个读取失败。": "%d saves, %d mismatched, %d failed to read.",
    "档位号 %d 超出 1..%d": "Slot number %d is outside 1..%d",
    "档位 %d <- %s (%d 帧)，来自 %s": "Slot %d <- %s (%d frames), from %s",
    "档位 %d 原本不在顺序表有效项里，已按档位号插回，count %d -> %d":
        "Slot %d was not among the valid order-table entries; re-inserted by slot number, count %d -> %d",
    "这些存档读取失败，已中止: ": "These saves failed to read, aborted: ",
    "忽略档位 %d (%s)：超出 1..%d": "Ignoring slot %d (%s): outside 1..%d",
    "档位 %d 有多个存档文件夹，取帧数较大的（游戏读档也取 max）": "Slot %d has several save folders; using the larger frame count (the game also takes the max)",
    "没有找到任何存档": "No saves found",
    "存在的档位 %d 个写入真实帧数，其余 %d 个写 0": "%d existing slots get real frame counts, the other %d get 0",
    "顺序表重置：count=30，顺序 0..29（游戏会自动跳过不存在的档位）": "Order table reset: count=30, order 0..29 (the game skips missing slots automatically)",
    "长度变了": "Length changed",
    "解码数据 0x%X 处的字节被意外修改 (%02X -> %02X)": "Byte at decoded offset 0x%X was modified unexpectedly (%02X -> %02X)",
    "档位  修改前              修改后": "Slot  Before               After",
    "  <- 变化": "  <- changed", "顺序表 count: %d -> %d%s": "Order table count: %d -> %d%s",
    "顺序表（0 起算下标；| 前为有效项，| 后为未用填充）": "Order table (0-based indices; entries before | are valid, after | are unused padding)",
    "  修改前: ": "  Before: ", "  修改后: ": "  After:  ",
    "总游玩时间(未改动): %s    上次光标: 档位下标 %d": "Total play time (unchanged): %s    Last cursor: slot index %d",
    "压缩后太长 (%d > %d)，放不下": "Too long after compression (%d > %d), does not fit",
    "输出大小不对": "Wrong output size", "签名校验失败": "Signature check failed", "seed 变了": "Seed changed",
    "重新解码的内容与预期不一致": "Re-decoded content does not match the expectation",
    "尾部标记丢了": "Tail marker lost",
    "加密不是解密的逆过程（输入文件异常）": "Encryption is not the inverse of decryption (abnormal input file)",
    "未知操作: ": "Unknown operation: ", "输出文件已存在，不覆盖: ": "Output file already exists, not overwriting: ",
    "hd_keys.json 里没有名为 %r 的 key（现有: %s）": "hd_keys.json has no key named %r (available: %s)",
    "无": "none", "需要 --key 或 --hd-key（或加 --dry-run 只看报告）": "--key or --hd-key is required (or add --dry-run to just see the report)",
    "\n已写出并校验通过:": "\nWritten and verified:",
    # --- language switch ---
    "English": "中文",
}
