
from pathlib import Path
import struct

from convert import parse_fdt

source = Path(r"C:\platform-tools\obsidian-live.dtb")
root, info = parse_fdt(source.read_bytes())

wanted = {
    "compatible",
    "reg",
    "interrupts",
    "interrupt-parent",
    "clock-frequency",
    "enable-method",
    "method",
    "ranges",
    "status",
    "device_type",
}

string_properties = {
    "compatible",
    "model",
    "device_type",
    "method",
    "status",
    "enable-method",
    "name",
}


def show_value(value, prop_name=""):
    if prop_name in string_properties:
        return repr(value.rstrip(b"\0").decode("utf-8", "replace"))

    if len(value) % 4 == 0 and len(value) > 0:
        cells = struct.unpack(">" + "I" * (len(value) // 4), value)
        return " ".join(f"0x{x:08x}" for x in cells)

    return value.hex()


def walk(node, path=""):
    name = node["source_name"]
    current = path + ("/" + name if name else "")

    props = dict(node["props"])
    compatible = props.get("compatible", b"")
    text = compatible.decode("utf-8", "ignore")

    interesting = (
        "gic" in text.lower()
        or "armv8-timer" in text.lower()
        or "psci" in text.lower()
        or "mt6789-timer" in text.lower()
        or name in ("interrupt-controller", "timer", "psci")
    )

    if interesting:
        print("\nNODE:", current or "/")

        for key in sorted(wanted):
            if key in props:
                print(f"  {key}: {show_value(props[key], key)}")

    for child in node["children"]:
        walk(child, current)


print("Searching platform nodes...")
walk(root)
