#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ngb_system_dat.py - Ninja Gaiden Black (Xbox, 5443000D) TDATA\\5443000d\\system.dat editor

The load-game list reads its per-slot play time and its display order from system.dat, not from
save000.dat. This module decodes system.dat, edits that table / order, and writes a re-signed copy.
Format and game logic: docs/system-dat-research.md

CLI (the input system.dat is never modified; output goes to resigned/<key>_<time>/TDATA/5443000d/system.dat):
  python ngb_system_dat.py show    <system.dat>
  python ngb_system_dat.py slot    <system.dat> <save folder>  (--key NAME | --hd-key HEX) [--dry-run]
  python ngb_system_dat.py sync    <system.dat> <5443000d>     (--key NAME | --hd-key HEX) [--dry-run]
  python ngb_system_dat.py order   <system.dat>                (--key NAME | --hd-key HEX) [--dry-run]
  python ngb_system_dat.py check   <5443000d>      (decoded vs legacy play time of every save)
"""
import os, re, struct, sys, time, argparse

from ngb_i18n import t
from ngb_save_manager import (APP_DIR, NAME_RE, OFF_PLAYTIME, SAVE_SIZE, SYSTEM_SIZE, TAIL, _hmac,
                              decrypt_save, encrypt_save, load_keys, parse_hd_key, read_meta_name,
                              roamable_sig, sign_raw)

# ---------------- Subbotin carryless range coder (verified against the game's own system.dat) ----------------
M=0xFFFFFFFF; TOP=1<<24; BOT=1<<16
def parse_freq(p):
    c=p[0]; f=[0]*257
    if c==0: return None,1
    if c==0xFF: f[:256]=p[1:257]; i=257
    else:
        i=1
        for _ in range(c): f[p[i]]=p[i+1]; i+=2
    f[256]=1; return f,i
def rc_decode(p,maxout):
    f,i=parse_freq(p)
    if f is None: return bytes(p[1:1+maxout])
    cum=[0]
    for x in f: cum.append(cum[-1]+x)
    tot=cum[257]; pos=i
    def rd():
        nonlocal pos
        b=p[pos] if pos<len(p) else 0xFF; pos+=1; return b
    low=0; code=0; rng=M
    for _ in range(4): code=((code<<8)|rd())&M
    out=bytearray()
    while pos<len(p) and len(out)<maxout:
        r=rng//tot; v=((code-low)&M)//r
        lo,hi=0,256
        while lo<hi:
            mid=(lo+hi)//2
            if cum[mid+1]>v: hi=mid
            else: lo=mid+1
        if lo==256: break
        out.append(lo); low=(low+r*cum[lo])&M; rng=(r*f[lo])&M
        while True:
            if (low^((low+rng)&M))<TOP: pass
            elif rng<BOT: rng=(-low)&(BOT-1)
            else: break
            code=((code<<8)|rd())&M; low=(low<<8)&M; rng=(rng<<8)&M
    return bytes(out)
def rc_encode(data,freq256):
    f=list(freq256)+[1]; cum=[0]
    for x in f: cum.append(cum[-1]+x)
    tot=cum[257]; out=bytearray([0xFF])+bytes(freq256); low=0; rng=M
    def put(s):
        nonlocal low,rng
        r=rng//tot; low=(low+r*cum[s])&M; rng=(r*f[s])&M
        while True:
            if (low^((low+rng)&M))<TOP: pass
            elif rng<BOT: rng=(-low)&(BOT-1)
            else: break
            out.append(low>>24); low=(low<<8)&M; rng=(rng<<8)&M
    for b in data:
        assert f[b]>0; put(b)
    put(256)
    for _ in range(4): out.append(low>>24); low=(low<<8)&M
    return bytes(out)
def make_freq(data,old):
    # 原频率表能覆盖所有出现过的字节就沿用（这样重新编码会与原文件逐字节相同）
    # (old may be None when the source stream had no 0xFF frequency table; then always rebuild)
    if old is not None and all(old[b] for b in set(data)): return list(old)
    cnt=[0]*256
    for b in data: cnt[b]+=1
    mx=max(cnt)
    return [max(1,min(255,c*255//mx)) if c else 0 for c in cnt]   # 重建的表 xemu 实机验证可用

# ---------------- system.dat layout ----------------
SYS_HEADER = 0x2A                       # fixed header at the start of the decoded stream
SYS_STRUCT = 0x508                      # structure that follows it
SYS_DECODED_LEN = SYS_HEADER + SYS_STRUCT
SYS_PLAIN_LEN = SYSTEM_SIZE - 0x18      # 0x538 bytes after decryption
SYS_MAGIC = 0x20030730
NSLOTS = 30
OFF_TOTAL_MS = 0x000                    # u32, total play time in ms
OFF_FRAMES = 0x004                      # u32[30], frames per slot (60 = 1 s), index = slot - 1
OFF_MAGIC = 0x07C                       # u32
OFF_COUNT = 0x1C6                       # u8, number of valid entries in the order table
OFF_ORDER = 0x1C7                       # u8[30], display order as 0-based slot indices
OFF_CURSOR = 0x1E5                      # u8, slot index the cursor was on last time
ORDER_REGION = (SYS_HEADER + OFF_COUNT, SYS_HEADER + OFF_CURSOR)      # absolute decoded range [lo, hi)
FRAMES_REGION = (SYS_HEADER + OFF_FRAMES, SYS_HEADER + OFF_FRAMES + 4 * NSLOTS)
# save000.dat decodes with the same coder; the frame count lives at struct +0x16628 (after the 0x2A header)
SAVE_FRAMES_OFF = SYS_HEADER + 0x16628
SAVE_SP_OFF = SYS_HEADER + 0x167AE        # u8 save-point number   (struct offsets read by default.xbe 0x179db0)
SAVE_CH_OFF = SYS_HEADER + 0x16817        # u8 0-based chapter
SAVE_KIND_OFF = SYS_HEADER + 0x1681A      # u8 story / tournament

def _u32(b, off): return struct.unpack_from("<I", b, off)[0]

def fmt_time(frames):
    s = frames // 60
    return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)

def fmt_ms(ms):
    s = ms // 1000
    return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)

# ---------------- parsing ----------------
class SystemDat:
    def __init__(self, raw, plain, decoded):
        self.raw, self.plain, self.decoded = raw, plain, decoded
        self.seed = _u32(raw, 0x14)

def _old_freq(plain):
    f, _ = parse_freq(plain)
    return None if f is None else f[:256]

def parse_system_dat(raw):
    if len(raw) != SYSTEM_SIZE: raise ValueError(t("system.dat 大小不对(%d)，应为 %d") % (len(raw), SYSTEM_SIZE))
    plain = decrypt_save(raw)
    if plain[-6:] != TAIL: raise ValueError(t("解密后尾部标记不对：不是本游戏的 system.dat，或文件已损坏"))
    dec = rc_decode(plain, SYS_DECODED_LEN)
    if len(dec) != SYS_DECODED_LEN: raise ValueError(t("解码后长度 0x%X，应为 0x%X") % (len(dec), SYS_DECODED_LEN))
    if dec[:6] != TAIL or b"TeamNINJA 2003" not in dec[:SYS_HEADER]: raise ValueError(t("解码后的头部不对"))
    if _u32(dec, SYS_HEADER + OFF_MAGIC) != SYS_MAGIC: raise ValueError(t("结构魔数不是 0x%08X") % SYS_MAGIC)
    st = read_state(dec)
    if st["count"] > NSLOTS or any(i >= NSLOTS for i in st["order"][:st["count"]]) or len(set(st["order"][:st["count"]])) != st["count"]:
        raise ValueError(t("顺序表内容不合法 (count=%d)") % st["count"])
    return SystemDat(raw, plain, dec)

def read_state(dec):
    s = dec[SYS_HEADER:]
    return {"total_ms": _u32(s, OFF_TOTAL_MS),
            "frames": list(struct.unpack_from("<%dI" % NSLOTS, s, OFF_FRAMES)),
            "count": s[OFF_COUNT], "order": list(s[OFF_ORDER:OFF_ORDER + NSLOTS]), "cursor": s[OFF_CURSOR]}

# ---------------- reading a save folder ----------------
def read_save(folder):
    """Slot number (from SaveMeta Name) and play-time frames (from the DECODED save000.dat) of one save folder.
    Also returns the legacy reading (raw plaintext 0x16653) for the consistency check."""
    name = read_meta_name(os.path.join(folder, "SaveMeta.xbx"))
    m = NAME_RE.match(name)
    if not m: raise ValueError(t("存档名格式不认识: %r") % name)
    raw = open(os.path.join(folder, "save000.dat"), "rb").read()
    if len(raw) != SAVE_SIZE: raise ValueError(t("save000.dat 大小不对(%d)") % len(raw))
    plain = decrypt_save(raw)
    if plain[-6:] != TAIL: raise ValueError(t("save000.dat 解密失败"))
    dec = rc_decode(plain, SAVE_KIND_OFF + 1)
    if len(dec) < SAVE_FRAMES_OFF + 4: raise ValueError(t("save000.dat 解码后太短(0x%X)") % len(dec))
    frames = _u32(dec, SAVE_FRAMES_OFF)
    return {"slot": int(m.group(1)), "name": name, "frames": frames, "legacy": _u32(plain, OFF_PLAYTIME), "folder": folder,
            "save_point": (dec[SAVE_CH_OFF], dec[SAVE_SP_OFF], dec[SAVE_KIND_OFF]) if len(dec) > SAVE_KIND_OFF else None}

def scan_saves(root):
    """read_save() for every save folder under root. Returns (list of results, list of (folder, error))."""
    ok, bad = [], []
    for e in sorted(os.listdir(root)):
        p = os.path.join(root, e)
        if not (os.path.isdir(p) and os.path.isfile(os.path.join(p, "SaveMeta.xbx")) and os.path.isfile(os.path.join(p, "save000.dat"))): continue
        try: ok.append(read_save(p))
        except Exception as ex: bad.append((e, str(ex)))
    return ok, bad

def check_saves(root):
    """Text report: does the legacy raw-plaintext play time equal the decoded one for each save?"""
    ok, bad = scan_saves(root)
    lines = [t("槽位  文件夹         解码后帧数  旧读法帧数  结果")]
    for r in sorted(ok, key=lambda r: r["slot"]):
        lines.append("%4d  %-13s %10d %10d  %s" % (r["slot"], os.path.basename(r["folder"]), r["frames"], r["legacy"], t("一致") if r["frames"] == r["legacy"] else t("不一致")))
    lines += [t("%s: 读取失败 (%s)") % b for b in bad]
    mism = sum(1 for r in ok if r["frames"] != r["legacy"])
    lines.append(t("共 %d 个存档，%d 个不一致，%d 个读取失败。") % (len(ok), mism, len(bad)))
    return "\n".join(lines)

# ---------------- edits (each returns the new decoded bytes, the byte ranges it may touch, notes) ----------------
def _insert_order(order, count, idx):
    """Put idx into order[:count] before the first larger entry; refill the unused tail ascending."""
    valid = order[:count]
    if idx in valid: return order, count
    pos = next((i for i, v in enumerate(valid) if v > idx), len(valid))
    valid = valid[:pos] + [idx] + valid[pos:]
    rest = [i for i in range(NSLOTS) if i not in valid]
    return valid + rest, len(valid)

def _put_order(buf, order, count):
    buf[SYS_HEADER + OFF_COUNT] = count
    buf[SYS_HEADER + OFF_ORDER:SYS_HEADER + OFF_ORDER + NSLOTS] = bytes(order)

def edit_slot(base, save_folder):
    r = read_save(save_folder)
    if not 1 <= r["slot"] <= NSLOTS: raise ValueError(t("档位号 %d 超出 1..%d") % (r["slot"], NSLOTS))
    idx = r["slot"] - 1; st = read_state(base.decoded); buf = bytearray(base.decoded)
    struct.pack_into("<I", buf, SYS_HEADER + OFF_FRAMES + 4 * idx, r["frames"])
    order, count = _insert_order(st["order"], st["count"], idx)
    _put_order(buf, order, count)
    allowed = [(SYS_HEADER + OFF_FRAMES + 4 * idx, SYS_HEADER + OFF_FRAMES + 4 * idx + 4), ORDER_REGION]
    notes = [t("档位 %d <- %s (%d 帧)，来自 %s") % (r["slot"], fmt_time(r["frames"]), r["frames"], os.path.basename(r["folder"]))]
    if idx not in st["order"][:st["count"]]: notes.append(t("档位 %d 原本不在顺序表有效项里，已按档位号插回，count %d -> %d") % (r["slot"], st["count"], count))
    return bytes(buf), allowed, notes

def edit_sync(base, root):
    saves, bad = scan_saves(root)
    if bad: raise ValueError(t("这些存档读取失败，已中止: ") + "; ".join("%s (%s)" % b for b in bad))
    notes, have = [], {}
    for r in saves:
        if not 1 <= r["slot"] <= NSLOTS: notes.append(t("忽略档位 %d (%s)：超出 1..%d") % (r["slot"], os.path.basename(r["folder"]), NSLOTS)); continue
        if r["slot"] in have:
            notes.append(t("档位 %d 有多个存档文件夹，取帧数较大的（游戏读档也取 max）") % r["slot"])
            have[r["slot"]] = max(have[r["slot"]], r["frames"])
        else: have[r["slot"]] = r["frames"]
    if not have: raise ValueError(t("没有找到任何存档"))
    buf = bytearray(base.decoded)
    struct.pack_into("<%dI" % NSLOTS, buf, SYS_HEADER + OFF_FRAMES, *[have.get(s, 0) for s in range(1, NSLOTS + 1)])
    notes.append(t("存在的档位 %d 个写入真实帧数，其余 %d 个写 0") % (len(have), NSLOTS - len(have)))
    return bytes(buf), [FRAMES_REGION], notes

def edit_order(base):
    buf = bytearray(base.decoded)
    _put_order(buf, list(range(NSLOTS)), NSLOTS)
    return bytes(buf), [ORDER_REGION], [t("顺序表重置：count=30，顺序 0..29（游戏会自动跳过不存在的档位）")]

def assert_only_changed(old, new, allowed):
    """Every byte outside the allowed ranges must be identical (header, total time, unlock/settings, cursor ...)."""
    if len(old) != len(new): raise AssertionError(t("长度变了"))
    for i, (a, b) in enumerate(zip(old, new)):
        if a != b and not any(lo <= i < hi for lo, hi in allowed):
            raise AssertionError(t("解码数据 0x%X 处的字节被意外修改 (%02X -> %02X)") % (i, a, b))

# ---------------- report ----------------
def _order_text(st):
    c = st["count"]
    return "%s | %s" % (",".join(map(str, st["order"][:c])), ",".join(map(str, st["order"][c:])))

def format_report(old_dec, new_dec):
    a, b = read_state(old_dec), read_state(new_dec)
    L = [t("档位  修改前              修改后"), "----  ------------------  ------------------"]
    for i in range(NSLOTS):
        fa, fb = a["frames"][i], b["frames"][i]
        L.append("%4d  %-18s  %-18s%s" % (i + 1, "%s (%d)" % (fmt_time(fa), fa), "%s (%d)" % (fmt_time(fb), fb), t("  <- 变化") if fa != fb else ""))
    L.append("")
    L.append(t("顺序表 count: %d -> %d%s") % (a["count"], b["count"], t("  <- 变化") if a["count"] != b["count"] else ""))
    L.append(t("顺序表（0 起算下标；| 前为有效项，| 后为未用填充）"))
    L.append(t("  修改前: ") + _order_text(a))
    L.append(t("  修改后: ") + _order_text(b) + (t("  <- 变化") if (a["order"], a["count"]) != (b["order"], b["count"]) else ""))
    L.append(t("总游玩时间(未改动): %s    上次光标: 档位下标 %d") % (fmt_ms(a["total_ms"]), a["cursor"]))
    return "\n".join(L)

# ---------------- write ----------------
def build_system_dat(base, new_dec, hd_key):
    """Re-encode new_dec, keep the original residue/tail, encrypt with the original seed, sign for hd_key."""
    freq = make_freq(new_dec, _old_freq(base.plain))
    stream = rc_encode(new_dec, freq)
    if len(stream) > SYS_PLAIN_LEN - 6: raise ValueError(t("压缩后太长 (%d > %d)，放不下") % (len(stream), SYS_PLAIN_LEN - 6))
    plain = stream + base.plain[len(stream):]
    raw = bytes(0x14) + struct.pack("<I", base.seed) + encrypt_save(plain, base.seed)
    return sign_raw(raw, hd_key)

def verify_system_dat(new_raw, base, new_dec, hd_key):
    if len(new_raw) != SYSTEM_SIZE: raise AssertionError(t("输出大小不对"))
    if _hmac(hd_key, roamable_sig(new_raw)) != new_raw[:0x14]: raise AssertionError(t("签名校验失败"))
    if new_raw[0x14:0x18] != base.raw[0x14:0x18]: raise AssertionError(t("seed 变了"))
    back = parse_system_dat(new_raw)
    if back.decoded != new_dec: raise AssertionError(t("重新解码的内容与预期不一致"))
    if back.plain[-6:] != TAIL: raise AssertionError(t("尾部标记丢了"))

OPS = ("slot", "sync", "order")

def plan(op, base_path, source=None):
    """Compute an edit without writing anything. Returns (base, new_decoded, notes, report_text)."""
    base = parse_system_dat(open(base_path, "rb").read())
    # the crypto round trip must be exact on the untouched input, otherwise nothing below can be trusted
    if encrypt_save(base.plain, base.seed) != base.raw[0x18:]: raise AssertionError(t("加密不是解密的逆过程（输入文件异常）"))
    if op == "slot": new, allowed, notes = edit_slot(base, source)
    elif op == "sync": new, allowed, notes = edit_sync(base, source)
    elif op == "order": new, allowed, notes = edit_order(base)
    else: raise ValueError(t("未知操作: ") + op)
    assert_only_changed(base.decoded, new, allowed)
    return base, new, notes, format_report(base.decoded, new)

def key_tag(name):
    return re.sub(r"[^0-9A-Za-z一-鿿]+", "_", name or "custom")

def apply(op, base_path, source, hd_key, tag, out_root=None):
    """plan() + write resigned/<tag>_<time>/TDATA/5443000d/system.dat + verify. Never overwrites an existing file."""
    base, new, notes, report = plan(op, base_path, source)
    out_dir = os.path.join(out_root or os.path.join(APP_DIR, "resigned"), "%s_%s" % (key_tag(tag), time.strftime("%Y%m%d_%H%M%S")), "TDATA", "5443000d")
    out = os.path.join(out_dir, "system.dat")
    if os.path.exists(out) or os.path.realpath(out) == os.path.realpath(base_path): raise ValueError(t("输出文件已存在，不覆盖: ") + out)
    new_raw = build_system_dat(base, new, hd_key)
    verify_system_dat(new_raw, base, new, hd_key)
    os.makedirs(out_dir)
    with open(out, "wb") as f: f.write(new_raw)
    verify_system_dat(open(out, "rb").read(), base, new, hd_key)          # and once more from disk
    return {"out": out, "notes": notes, "report": report}

# ---------------- CLI ----------------
def _resolve_key(args):
    if args.hd_key: return parse_hd_key(args.hd_key), "custom"
    keys = load_keys()
    if args.key not in keys: raise SystemExit(t("hd_keys.json 里没有名为 %r 的 key（现有: %s）") % (args.key, ", ".join(keys) or t("无")))
    return keys[args.key], args.key

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try: stream.reconfigure(encoding="utf-8")        # Chinese report text on a cp932/cp936 console
        except Exception: pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def add(name, src=None):
        p = sub.add_parser(name); p.add_argument("system_dat")
        if src: p.add_argument(src)
        if name != "show":
            g = p.add_mutually_exclusive_group(); g.add_argument("--key", help="name in hd_keys.json"); g.add_argument("--hd-key", help="32 hex chars")
            p.add_argument("--dry-run", action="store_true", help="only print the before/after report")
            p.add_argument("--out-root", help="default: <app folder>/resigned")
    add("show"); add("slot", "save_folder"); add("sync", "udata_root"); add("order")
    sub.add_parser("check").add_argument("udata_root")
    a = ap.parse_args(argv)
    if a.cmd == "check": print(check_saves(a.udata_root)); return 0
    src = getattr(a, "save_folder", None) or getattr(a, "udata_root", None)
    if a.cmd == "show":
        base = parse_system_dat(open(a.system_dat, "rb").read()); print(format_report(base.decoded, base.decoded)); return 0
    base, new, notes, report = plan(a.cmd, a.system_dat, src)
    print(report); print(); print("\n".join(notes))
    if a.dry_run: return 0
    if not (a.key or a.hd_key): raise SystemExit(t("需要 --key 或 --hd-key（或加 --dry-run 只看报告）"))
    key, tag = _resolve_key(a)
    res = apply(a.cmd, a.system_dat, src, key, tag, a.out_root)
    print(t("\n已写出并校验通过:"), res["out"]); return 0

if __name__ == "__main__":
    sys.exit(main())
