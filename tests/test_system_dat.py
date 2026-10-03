"""
Tests for the system.dat codec / editor.

Synthetic tests (always run) build their own system.dat and save folders with a throw-away HD key.
Real-data tests are skipped unless these environment variables point at your own files (never committed):
  NGB_TEST_SYSTEM_DAT   path to a system.dat copied from the game
  NGB_TEST_UDATA        path to the matching ...\\UDATA\\5443000d folder (optional, enables the save tests)
"""
import os, random, struct

import pytest

import ngb_system_dat as SD
from ngb_save_manager import (SAVE_SIZE, SYSTEM_SIZE, TAIL, _hmac, decrypt_save, encrypt_save, folder_id,
                              roamable_sig, sign_raw)

TEST_KEY = bytes(range(1, 17))          # throw-away key, not any real console's
OTHER_KEY = bytes(range(101, 117))


# ---------------- synthetic builders ----------------
def _frames_bytes(frames): return struct.pack("<%dI" % SD.NSLOTS, *frames)

def build_decoded(frames, order, count, total_ms=123456, cursor=2):
    s = bytearray(SD.SYS_STRUCT)
    for i in range(0x80, 0x1C0): s[i] = ((i * 31 + 7) % 5) * 17      # stand-in for unlocks / settings: must survive every edit
    for i in range(0x1E6, SD.SYS_STRUCT): s[i] = ((i * 13 + 5) % 4) * 29
    struct.pack_into("<I", s, SD.OFF_TOTAL_MS, total_ms)
    struct.pack_into("<%dI" % SD.NSLOTS, s, SD.OFF_FRAMES, *frames)
    struct.pack_into("<I", s, SD.OFF_MAGIC, SD.SYS_MAGIC)
    s[SD.OFF_COUNT] = count; s[SD.OFF_ORDER:SD.OFF_ORDER + SD.NSLOTS] = bytes(order); s[SD.OFF_CURSOR] = cursor
    return TAIL + b"TeamNINJA 2003" + bytes(SD.SYS_HEADER - 6 - 14) + bytes(s)

def _freq_from(data, cover_all):
    cnt = [0] * 256
    for b in data: cnt[b] += 1
    mx = max(cnt)
    return [max(1, min(255, c * 255 // mx)) if (c or cover_all) else 0 for c in cnt]    # cover_all: every byte value encodable

def build_raw(decoded, plain_len, seed, key, cover_all=False):
    stream = SD.rc_encode(decoded, _freq_from(decoded, cover_all))
    filler = bytes((i * 7 + 3) & 0xFF for i in range(plain_len))
    plain = stream + filler[len(stream):plain_len - 6] + TAIL
    raw = bytes(0x14) + struct.pack("<I", seed) + encrypt_save(plain, seed)
    return sign_raw(raw, key)

def make_system(frames=None, order=None, count=None, cover_all=False, **kw):
    frames = frames if frames is not None else [(i + 1) * 3600 for i in range(SD.NSLOTS)]
    order = order if order is not None else list(range(SD.NSLOTS))
    count = SD.NSLOTS if count is None else count
    return build_raw(build_decoded(frames, order, count, **kw), SD.SYS_PLAIN_LEN, 0x1234ABCD, TEST_KEY, cover_all)

def make_save_folder(root, slot, frames, seed=0xC0FFEE):
    name = "%d. CHAPTER 3 000:05" % slot
    folder = os.path.join(str(root), folder_id(name)); os.makedirs(folder)
    with open(os.path.join(folder, "SaveMeta.xbx"), "wb") as f:
        f.write(b"\xff\xfe" + ("Name=%s\r\nNoCopy=1" % name).encode("utf-16-le"))
    rnd = random.Random(slot)
    dec = bytearray(TAIL + bytes(SD.SYS_HEADER - 6) + bytes(rnd.randrange(16) for _ in range(SD.SAVE_FRAMES_OFF + 0x100 - SD.SYS_HEADER)))
    struct.pack_into("<I", dec, SD.SAVE_FRAMES_OFF, frames)
    raw = build_raw(bytes(dec), SAVE_SIZE - 0x18, seed, TEST_KEY)
    with open(os.path.join(folder, "save000.dat"), "wb") as f: f.write(raw)
    return folder


# ---------------- codec ----------------
@pytest.mark.parametrize("n", [1, 2, 5, 100, 0x532, 5000])
@pytest.mark.parametrize("cover_all", [False, True])
def test_rc_roundtrip(n, cover_all):
    rnd = random.Random(n)
    data = bytes(rnd.choice([0, 0, 0, 1, 2, 3, 0x94, 0xFF]) for _ in range(n))
    stream = SD.rc_encode(data, _freq_from(data, cover_all))
    # the game's buffer always has residue after the stream (the decoder also stops when the input runs out)
    assert SD.rc_decode(stream + bytes(20), len(data) + 50) == data      # stops at EOF, not at the cap
    assert SD.rc_decode(stream + bytes(20), len(data)) == data

def test_rc_decode_respects_output_cap():
    data = bytes(range(64)) * 4
    stream = SD.rc_encode(data, _freq_from(data, True)) + bytes(20)
    assert SD.rc_decode(stream, 100) == data[:100]

def test_parse_freq_formats():
    f, i = SD.parse_freq(bytes([2, 7, 9, 200, 33]))
    assert i == 5 and f[7] == 9 and f[200] == 33 and f[256] == 1 and sum(f) == 43
    assert SD.parse_freq(bytes([0, 1, 2, 3])) == (None, 1)
    assert SD.rc_decode(bytes([0, 10, 20, 30, 40]), 3) == bytes([10, 20, 30])    # 0x00 = stored

def test_make_freq_keeps_old_table_when_it_covers_data():
    old = [5] * 256
    assert SD.make_freq(b"\x01\x02", old) == old
    rebuilt = SD.make_freq(b"\x01\x01\x02", [0] * 255 + [9])
    assert rebuilt[1] == 255 and rebuilt[2] == 127 and rebuilt[0] == 0
    assert SD.make_freq(b"\x01", None)[1] == 255

def test_encrypt_is_inverse_of_decrypt():
    rnd = random.Random(1)
    raw = bytes(0x14) + struct.pack("<I", 0xDEADBEEF) + bytes(rnd.randrange(256) for _ in range(SYSTEM_SIZE - 0x18))
    assert encrypt_save(decrypt_save(raw), 0xDEADBEEF) == raw[0x18:]
    plain = bytes(rnd.randrange(256) for _ in range(0x538))
    assert decrypt_save(bytes(0x14) + struct.pack("<I", 7) + encrypt_save(plain, 7)) == plain


# ---------------- parse / state ----------------
def test_parse_synthetic():
    raw = make_system(order=[3, 1, 2] + [0] + list(range(4, 30)), count=3)
    b = SD.parse_system_dat(raw)
    st = SD.read_state(b.decoded)
    assert len(b.decoded) == SD.SYS_DECODED_LEN and st["count"] == 3 and st["order"][:3] == [3, 1, 2]
    assert st["frames"][4] == 5 * 3600 and b.seed == 0x1234ABCD

def test_reencode_with_original_table_is_identical():
    raw = make_system(cover_all=True)
    b = SD.parse_system_dat(raw)
    stream = SD.rc_encode(b.decoded, SD.make_freq(b.decoded, SD._old_freq(b.plain)))
    assert b.plain[:len(stream)] == stream
    assert encrypt_save(b.plain, b.seed) == raw[0x18:]

@pytest.mark.parametrize("mutate", ["size", "tail", "magic", "count"])
def test_parse_rejects_bad_input(mutate):
    raw = make_system()
    if mutate == "size": raw = raw[:-1]
    elif mutate == "tail": raw = raw[:-1] + bytes([raw[-1] ^ 1])
    elif mutate == "magic": raw = make_system()[:0x18] + bytes(SYSTEM_SIZE - 0x18)
    else: raw = build_raw(build_decoded([0] * 30, list(range(30)), 31), SD.SYS_PLAIN_LEN, 5, TEST_KEY)
    with pytest.raises(ValueError):
        SD.parse_system_dat(raw)


# ---------------- order logic ----------------
@pytest.mark.parametrize("order,count,idx,exp_valid", [
    ([0, 1, 2, 3, 4], 5, 7, [0, 1, 2, 3, 4, 7]),                       # bigger than everything: append
    ([0, 2, 4], 3, 3, [0, 2, 3, 4]),                                   # before the first larger index
    ([5, 1, 9], 3, 3, [3, 5, 1, 9]),                                   # first larger entry in display order (5), not the next sorted one
    ([4, 2], 2, 0, [0, 4, 2]),
    ([0, 1, 2], 3, 1, [0, 1, 2]),                                      # already present: untouched
])
def test_insert_order(order, count, idx, exp_valid):
    full = order + [i for i in range(30) if i not in order]
    new, c = SD._insert_order(full, count, idx)
    assert new[:c] == exp_valid and c == len(exp_valid)
    assert new[c:] == sorted(set(range(30)) - set(exp_valid)) or c == count      # fill ascending when we rebuilt it
    assert sorted(new) == list(range(30))


# ---------------- operations ----------------
def _plan(tmp_path, op, raw, source=None):
    p = tmp_path / "system.dat"; p.write_bytes(raw)
    return SD.plan(op, str(p), source)

def _changed_bytes(a, b): return {i for i in range(len(a)) if a[i] != b[i]}

def test_slot_update_inserts_missing_slot(tmp_path):
    udata = tmp_path / "UDATA"; udata.mkdir()
    folder = make_save_folder(udata, 5, 251)
    order = [0, 1, 2, 3, 5, 6, 7] + [4] + list(range(8, 30))        # slot 5 (index 4) is not in the valid part
    raw = make_system(order=order, count=7)
    base, new, notes, report = _plan(tmp_path, "slot", raw, folder)
    a, b = SD.read_state(base.decoded), SD.read_state(new)
    assert b["frames"][4] == 251 and b["count"] == 8 and b["order"][:8] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert b["order"][8:] == list(range(8, 30))
    assert [i for i in range(30) if a["frames"][i] != b["frames"][i]] == [4]
    assert a["total_ms"] == b["total_ms"] and a["cursor"] == b["cursor"]
    allowed = set(range(SD.SYS_HEADER + SD.OFF_FRAMES + 16, SD.SYS_HEADER + SD.OFF_FRAMES + 20)) | set(range(*SD.ORDER_REGION))
    assert _changed_bytes(base.decoded, new) <= allowed
    assert "0:00:04" in report and "变化" in report

def test_slot_update_keeps_order_when_slot_present(tmp_path):
    udata = tmp_path / "UDATA"; udata.mkdir()
    folder = make_save_folder(udata, 3, 600)
    raw = make_system(order=[2, 0, 1] + list(range(3, 30)), count=30)
    base, new, _, _ = _plan(tmp_path, "slot", raw, folder)
    frame_bytes = set(range(SD.SYS_HEADER + SD.OFF_FRAMES + 8, SD.SYS_HEADER + SD.OFF_FRAMES + 12))
    assert _changed_bytes(base.decoded, new) <= frame_bytes              # order table not touched at all
    assert SD.read_state(new)["frames"][2] == 600

def test_sync_writes_real_frames_and_zero(tmp_path):
    udata = tmp_path / "UDATA"; udata.mkdir()
    for slot, fr in ((1, 100), (7, 4000), (30, 99999)): make_save_folder(udata, slot, fr)
    base, new, notes, _ = _plan(tmp_path, "sync", make_system(), str(udata))
    b = SD.read_state(new)
    assert [b["frames"][i] for i in range(30) if b["frames"][i]] == [100, 4000, 99999]
    assert b["frames"][0] == 100 and b["frames"][6] == 4000 and b["frames"][29] == 99999
    assert _changed_bytes(base.decoded, new) <= set(range(*SD.FRAMES_REGION))
    a = SD.read_state(base.decoded)
    assert (a["count"], a["order"]) == (b["count"], b["order"])

def test_sync_with_no_saves_is_refused(tmp_path):
    (tmp_path / "UDATA").mkdir()
    with pytest.raises(ValueError):
        _plan(tmp_path, "sync", make_system(), str(tmp_path / "UDATA"))

def test_reset_order(tmp_path):
    raw = make_system(order=[5, 3, 1] + [0, 2, 4] + list(range(6, 30)), count=3)
    base, new, _, report = _plan(tmp_path, "order", raw)
    b = SD.read_state(new)
    assert b["count"] == 30 and b["order"] == list(range(30))
    assert _changed_bytes(base.decoded, new) <= set(range(*SD.ORDER_REGION))
    assert "3 -> 30" in report

def test_assert_only_changed_catches_stray_edit():
    dec = build_decoded([0] * 30, list(range(30)), 30)
    bad = bytearray(dec); bad[SD.SYS_HEADER + 0x100] ^= 0xFF
    with pytest.raises(AssertionError):
        SD.assert_only_changed(dec, bytes(bad), [SD.FRAMES_REGION])
    SD.assert_only_changed(dec, bytes(bad), [(SD.SYS_HEADER + 0x100, SD.SYS_HEADER + 0x101)])


# ---------------- writing ----------------
@pytest.mark.parametrize("cover_all", [True, False])     # False: edited bytes are not in the old table -> table is rebuilt
def test_apply_writes_verified_resigned_copy(tmp_path, cover_all):
    udata = tmp_path / "UDATA"; udata.mkdir()
    make_save_folder(udata, 2, 123456789)
    src = tmp_path / "system.dat"; raw = make_system(cover_all=cover_all, frames=[(i % 7) * 600 for i in range(30)])
    src.write_bytes(raw)
    res = SD.apply("sync", str(src), str(udata), OTHER_KEY, "my key!", out_root=str(tmp_path / "resigned"))
    out = res["out"]
    rel = os.path.relpath(out, str(tmp_path / "resigned")).replace("\\", "/").split("/")
    assert len(rel) == 4 and rel[1:] == ["TDATA", "5443000d", "system.dat"]
    assert "my_key" in out
    assert src.read_bytes() == raw                                       # input untouched
    new_raw = open(out, "rb").read()
    assert len(new_raw) == SYSTEM_SIZE
    assert _hmac(OTHER_KEY, roamable_sig(new_raw)) == new_raw[:0x14]     # signed for the target key
    assert new_raw[0x14:0x18] == raw[0x14:0x18]                          # same seed
    back = SD.parse_system_dat(new_raw)
    assert SD.read_state(back.decoded)["frames"][1] == 123456789
    assert back.plain[-6:] == TAIL and back.plain[-6:] == SD.parse_system_dat(raw).plain[-6:]

def test_apply_never_overwrites(tmp_path, monkeypatch):
    src = tmp_path / "system.dat"; src.write_bytes(make_system())
    monkeypatch.setattr(SD.time, "strftime", lambda fmt: "20260101_000000")
    SD.apply("order", str(src), None, TEST_KEY, "k", out_root=str(tmp_path / "r"))
    with pytest.raises(ValueError):
        SD.apply("order", str(src), None, TEST_KEY, "k", out_root=str(tmp_path / "r"))

def test_cli_dry_run_and_write(tmp_path, capsys):
    src = tmp_path / "system.dat"; src.write_bytes(make_system(order=[1, 0] + list(range(2, 30)), count=2))
    assert SD.main(["order", str(src), "--dry-run"]) == 0
    assert "count: 2 -> 30" in capsys.readouterr().out
    assert not (tmp_path / "resigned").exists()
    assert SD.main(["order", str(src), "--hd-key", TEST_KEY.hex(), "--out-root", str(tmp_path / "o")]) == 0
    assert "已写出并校验通过" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        SD.main(["order", str(src)])                                     # no key, not dry-run


# ---------------- real data (env vars, skipped otherwise) ----------------
real_sys = os.environ.get("NGB_TEST_SYSTEM_DAT")
real_udata = os.environ.get("NGB_TEST_UDATA")
needs_sys = pytest.mark.skipif(not real_sys or not os.path.isfile(real_sys or ""), reason="NGB_TEST_SYSTEM_DAT not set")
needs_udata = pytest.mark.skipif(not real_udata or not os.path.isdir(real_udata or ""), reason="NGB_TEST_UDATA not set")

@needs_sys
def test_real_system_dat_roundtrip():
    raw = open(real_sys, "rb").read()
    b = SD.parse_system_dat(raw)
    assert encrypt_save(b.plain, b.seed) == raw[0x18:]                   # encrypt(decrypt(x)) == x
    freq = SD.make_freq(b.decoded, SD._old_freq(b.plain))
    assert freq == SD._old_freq(b.plain)                                 # the original table covers its own data
    stream = SD.rc_encode(b.decoded, freq)
    assert b.plain[:len(stream)] == stream                               # decode -> re-encode == original prefix
    assert b.plain[-6:] == TAIL

@needs_sys
def test_real_system_dat_order_reset_and_slot_only_edits(tmp_path):
    raw = open(real_sys, "rb").read(); b = SD.parse_system_dat(raw)
    src = tmp_path / "system.dat"; src.write_bytes(raw)
    res = SD.apply("order", str(src), None, TEST_KEY, "t", out_root=str(tmp_path / "o"))
    back = SD.parse_system_dat(open(res["out"], "rb").read())
    assert _changed_bytes(b.decoded, back.decoded) <= set(range(*SD.ORDER_REGION))
    assert SD.read_state(back.decoded)["frames"] == SD.read_state(b.decoded)["frames"]

@needs_udata
def test_real_saves_decoded_frames_match_legacy_reading():
    saves, bad = SD.scan_saves(real_udata)
    assert saves and not bad
    assert all(s["frames"] == s["legacy"] for s in saves)

@needs_sys
@needs_udata
def test_real_sync_changes_only_frame_table(tmp_path):
    raw = open(real_sys, "rb").read()
    src = tmp_path / "system.dat"; src.write_bytes(raw)
    res = SD.apply("sync", str(src), real_udata, TEST_KEY, "t", out_root=str(tmp_path / "o"))
    base = SD.parse_system_dat(raw); back = SD.parse_system_dat(open(res["out"], "rb").read())
    assert _changed_bytes(base.decoded, back.decoded) <= set(range(*SD.FRAMES_REGION))
    saves, _ = SD.scan_saves(real_udata)
    frames = SD.read_state(back.decoded)["frames"]
    for s in saves:
        if 1 <= s["slot"] <= 30: assert frames[s["slot"] - 1] == s["frames"]
