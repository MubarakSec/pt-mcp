# pt-mcp — self-contained read + build MCP server for Packet Tracer

**This folder is the whole toolkit.** No external projects, no third-party
packages, no Node/Bun. Copy it anywhere and it still works. 192 KB total.

```
pt-mcp/
├── server.py       MCP server (stdio JSON-RPC 2.0) — 21 tools
├── ptbuild.py      topology builder: clone / cable / note / delete / config
├── ptread.py       topology reader: devices / links / configs / notes
├── unpacket.py     .pkt  → XML   (CLI)
├── repacket.py     XML  → .pkt  (CLI)
├── smoke.py        handshake test
├── README.md
└── Decipher/       vendored crypto (from Punkcake21/Unpacket, MIT)
    ├── pt_crypto.py   pipeline entry point
    ├── twofish.py     Twofish block cipher
    ├── eax.py         EAX authenticated encryption
    ├── cmac.py        CMAC (OMAC-1)
    └── ctr.py         CTR keystream
```

## How it works

Cisco's `.pkt` is a four-layer encrypted envelope wrapped around plain XML:

```
.pkt
 ├─ 1  reverse bytes + positional XOR mask     obfuscation
 ├─ 2  Twofish in EAX mode                     real crypto
 │      · CMAC builds the auth tag (OMAC 0/1/2)
 │      · CTR keystream seeded from the nonce MAC
 ├─ 3  secondary XOR, decreasing counter       obfuscation
 └─ 4  qCompress = zlib + 4-byte BE length     compression
        ▼
   plain XML  PACKETTRACER5 → NETWORK → DEVICES / LINKS / …
```

`unpacket` peels it, `repacket` re-seals it. The XML *is* the topology, so
nothing ever has to be drawn in a GUI.

**The catch:** devices are not linked by name. Every device owns a
`SAVE_REF_ID`, and cables, PDUs and scenarios all key on it. Cloning one
therefore means minting a fresh ref id, MAC/BIA, serial and session memory
pointers — that's what `ptbuild.py` does for you.

## Commands

```bash
python3 server.py                 # run the MCP server on stdio
unpacket lab.pkt -o lab.xml       # CLI: decode
repacket lab.xml -o out.pkt       # CLI: rebuild
ptread lab.xml                    # CLI: report a topology
```

## Safety model

- **Read tools** (`pt_*`) never write anything except a cached XML copy in
  `/tmp/pt-mcp-cache/`.
- **Build tools** (`pt_build_*`) work on a **copy**; `pt_build_open` never
  touches the source `.pkt`.
- `pt_build_save` **refuses to overwrite the source lab** unless you pass
  `allow_overwrite: true` explicitly.

## Tools (21)

### Read (11)
`pt_list_files` `pt_open` `pt_overview` `pt_devices` `pt_device_detail`
`pt_config` `pt_links` `pt_notes` `pt_pdus` `pt_search` `pt_command_logs`

### Build (10)
| Tool | What it does |
|---|---|
| `pt_build_open` | start an editable copy of a `.pkt` |
| `pt_build_status` | diff vs. the original + operation log |
| `pt_build_clone` | duplicate a device under a new name/position/MAC |
| `pt_build_cable` | connect two devices by interface name |
| `pt_build_note` | add a canvas note |
| `pt_build_rename` | rename a device |
| `pt_build_delete_device` | remove a device + all cables touching it |
| `pt_build_delete_cable` | remove cables between two devices |
| `pt_build_set_config` | replace a device's saved CLI |
| `pt_build_save` | write XML + repacket to a `.pkt` |

## Known limits

- **`pt_build_clone` only duplicates models already present in the file.** A
  brand-new device *model* needs a hand-written `MODULE`/`PORT` tree. Not
  implemented. Workaround: seed the file once from PT with one of each model,
  then clone freely.
- `pt_build_set_config` writes the same text to `STARTUPCONFIG` and
  `RUNNINGCONFIG`. A device that was running shows a mismatched config until
  PT reboots it.
- No live validation. The server cannot ping or check convergence — Packet
  Tracer itself is the only simulator.

## Registered in
`~/.config/opencode/opencode.json` → `mcp.servers["pt-mcp"]`

## Verified
Against PT **9.0.1.0858**: decode → clone → cable → note → set config →
repack → **opened in Packet Tracer with the new device on the canvas**.

## Licence
Crypto layer is MIT, from [Punkcake21/Unpacket](https://github.com/Punkcake21/Unpacket).
Not affiliated with or endorsed by Cisco. For educational and interoperability use.
