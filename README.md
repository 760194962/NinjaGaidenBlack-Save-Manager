# NinjaGaidenBlack-Save-Manager

Save manager for **Ninja Gaiden Black (original Xbox, TitleID `5443000D`)**.
Instead of 12-hex folder names, see what each save actually is: slot, chapter, play time, difficulty. Works on saves from a real Xbox, xemu, or Xbox 360 back-compat.

忍者龙剑传 黑（初代 Xbox）存档管理器：直接显示每个存档的槽位、章节、游玩时间、难度，不用再对着一堆 12 位十六进制文件夹名猜。

## Features / 功能
- Reads slot / chapter / play time (to the second) / difficulty / mode for every save (no keys needed)
- Move a save to another slot (rewrites SaveMeta and renames the folder to the correct hash)
- Re-sign saves with an XboxHDKey (move between console / xemu / Xbox 360); also re-signs `TDATA\5443000d\system.dat` (settings, 1,360 bytes) if it sits next to the UDATA folder. Output goes to `resigned/<key>_<time>/UDATA` and `/TDATA`
- Multi-select, copy selected saves to another folder, or copy to clipboard
- Open a single save's folder; per-save notes (stored in `save_notes.json`, never inside the save)
- CSV export; CLI version `ngb_save_info.py`

## Usage
Requires Python 3.8+ with tkinter (included in the Windows installer).

```
python ngb_save_manager.py            # GUI; or double-click 启动存档管理器.bat
python ngb_save_manager.py --selftest <5443000d folder>
python ngb_save_info.py <5443000d folder> [--csv out.csv]
```
Point it at `UDATA\5443000d` (or its parent). Moves and re-signs make a backup in `backups/` next to the script.

HD keys: `hd_keys.json` (created on first run, git-ignored) holds `{"name": "32 hex chars"}`. No keys are bundled; add your own console or xemu key there.

## How it works
Folder name = XDK `XCreateSaveGame` hash of the save name; `save000.dat` is NinjaCrypt-encrypted and HMAC-signed with the console HD key. Details in [docs/save-format-research.md](docs/save-format-research.md) (Chinese).

## Known limits
- Save-point names and chapter titles are not shown: the save only stores IDs, and the ID→name table is not decoded yet.
- The in-game list order appears to follow directory order, not slot number (unverified in xemu).

## Credits
Encryption format from [feudalnate/NinjaCrypt](https://github.com/feudalnate/ninjacrypt) (Unlicense). Make backups before touching real saves; use at your own risk.

## License
MIT
