
#!/usr/bin/env python3
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9

MAX_PROPERTY_NAME = 31
MAX_NODE_NAME = 63


def align4(value):
    return (value + 3) & ~3


def read_c_string(data, offset, limit):
    if offset < 0 or offset >= limit:
        raise ValueError("String offset outside permitted region")

    end = data.find(b"\0", offset, limit)
    if end < 0:
        raise ValueError("Unterminated string")

    return data[offset:end]


def parse_fdt(blob):
    if len(blob) < 40:
        raise ValueError("File is too small to be an FDT")

    header = struct.unpack_from(">10I", blob, 0)

    (
        magic, total_size, struct_off, strings_off, reserve_off,
        version, last_compatible, boot_cpu,
        strings_size, struct_size
    ) = header

    if magic != FDT_MAGIC:
        raise ValueError("Invalid FDT magic")

    if total_size > len(blob) or total_size < 40:
        raise ValueError("Invalid FDT total size")

    if version < 16:
        raise ValueError("Unsupported old FDT version")

    struct_end = struct_off + struct_size
    strings_end = strings_off + strings_size

    if struct_off < 40 or struct_end > total_size:
        raise ValueError("Invalid FDT structure block")

    if strings_off < 40 or strings_end > total_size:
        raise ValueError("Invalid FDT strings block")

    if reserve_off < 40 or reserve_off + 16 > total_size:
        raise ValueError("Invalid FDT reserve map offset")

    strings = blob[strings_off:strings_end]
    pos = struct_off

    def read_u32():
        nonlocal pos

        if pos + 4 > struct_end:
            raise ValueError("Unexpected end of structure block")

        value = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        return value

    def parse_node():
        nonlocal pos

        token = read_u32()

        if token != FDT_BEGIN_NODE:
            raise ValueError("Expected BEGIN_NODE")

        end = blob.find(b"\0", pos, struct_end)

        if end < 0:
            raise ValueError("Unterminated FDT node name")

        node_name = blob[pos:end].decode("utf-8", "strict")
        pos = align4(end + 1)

        if pos > struct_end:
            raise ValueError("Node name exceeds structure block")

        node = {
            "source_name": node_name,
            "props": [],
            "children": []
        }

        while True:
            token = read_u32()

            if token == FDT_PROP:
                length = read_u32()
                name_offset = read_u32()

                if name_offset >= len(strings):
                    raise ValueError("Invalid property name offset")

                prop_name = read_c_string(
                    strings, name_offset, len(strings)
                ).decode("utf-8", "strict")

                if pos + length > struct_end:
                    raise ValueError("Property exceeds structure block")

                value = blob[pos:pos + length]
                pos = align4(pos + length)

                if pos > struct_end:
                    raise ValueError("Property padding exceeds structure block")

                node["props"].append((prop_name, value))

            elif token == FDT_BEGIN_NODE:
                pos -= 4
                node["children"].append(parse_node())

            elif token == FDT_END_NODE:
                return node

            elif token == FDT_NOP:
                continue

            else:
                raise ValueError(f"Unexpected FDT token: {token}")

    if read_u32() != FDT_BEGIN_NODE:
        raise ValueError("FDT root node missing")

    pos -= 4
    root = parse_node()

    if read_u32() != FDT_END:
        raise ValueError("Missing FDT_END token")

    # Read the FDT reserve map. It is reported but not converted
    # into Apple DT properties.
    reserve_entries = []
    reserve_pos = reserve_off

    while reserve_pos + 16 <= total_size:
        address, size = struct.unpack_from(">QQ", blob, reserve_pos)
        reserve_pos += 16

        if address == 0 and size == 0:
            break

        reserve_entries.append({
            "address": f"0x{address:x}",
            "size": f"0x{size:x}"
        })
    else:
        raise ValueError("Unterminated FDT reserve map")

    return root, {
        "version": version,
        "last_compatible_version": last_compatible,
        "total_size": total_size,
        "boot_cpu": boot_cpu,
        "reserve_entries": reserve_entries,
        "reserve_entry_count": len(reserve_entries)
    }


def prepare_tree(node, is_root=False, rename_map=None, path=""):
    if rename_map is None:
        rename_map = {}

    source_name = node["source_name"]
    apple_name = "device-tree" if is_root else source_name

    encoded_node_name = apple_name.encode("utf-8")

    if len(encoded_node_name) > MAX_NODE_NAME:
        raise ValueError(f"Apple node name too long: {apple_name}")

    current_path = path + "/" + apple_name

    props = []
    seen = set()

    # Apple Device Tree uses a "name" property for every node.
    props.append(("name", encoded_node_name + b"\0"))
    seen.add("name")

    for prop_name, value in node["props"]:
        if prop_name == "name":
            continue

        encoded = prop_name.encode("utf-8")
        output_name = prop_name

        if len(encoded) > MAX_PROPERTY_NAME:
            digest = hashlib.sha256(
                (current_path + "\0" + prop_name).encode("utf-8")
            ).hexdigest()[:8]

            prefix = encoded[:22].decode("ascii", "ignore")
            output_name = prefix + "_" + digest

            if len(output_name.encode("ascii")) > MAX_PROPERTY_NAME:
                raise ValueError("Generated alias exceeds Apple limit")

            rename_map[current_path + ":" + prop_name] = output_name

        if output_name in seen:
            raise ValueError(
                f"Property name collision at {current_path}: {output_name}"
            )

        if len(value) > 0xFFFFFFFF:
            raise ValueError(f"Property too large: {prop_name}")

        props.append((output_name, value))
        seen.add(output_name)

    return {
        "name": apple_name,
        "props": props,
        "children": [
            prepare_tree(
                child,
                rename_map=rename_map,
                path=current_path
            )
            for child in node["children"]
        ]
    }


def serialize_node(node):
    props = node["props"]
    children = node["children"]

    if len(props) > 0xFFFFFFFF or len(children) > 0xFFFFFFFF:
        raise ValueError("Too many node entries")

    output = bytearray(
        struct.pack("<II", len(props), len(children))
    )

    for name, value in props:
        name_bytes = name.encode("ascii")

        if len(name_bytes) > MAX_PROPERTY_NAME:
            raise ValueError(f"Property name too long: {name}")

        header = name_bytes.ljust(32, b"\0")

        output += header
        output += struct.pack("<I", len(value))
        output += value
        output += b"\0" * (align4(len(value)) - len(value))

    for child in children:
        output += serialize_node(child)

    return bytes(output)


def validate_apple_tree(data):
    pos = 0
    node_count = 0
    property_count = 0

    def parse():
        nonlocal pos, node_count, property_count

        if pos + 8 > len(data):
            raise ValueError("Truncated Apple DT node")

        nprops, nchildren = struct.unpack_from("<II", data, pos)
        pos += 8
        node_count += 1

        if nprops > 100000 or nchildren > 100000:
            raise ValueError("Unreasonable node counts")

        names = set()
        node_name = None

        for _ in range(nprops):
            if pos + 36 > len(data):
                raise ValueError("Truncated Apple DT property header")

            raw_name = data[pos:pos + 32]
            length = struct.unpack_from("<I", data, pos + 32)[0]
            pos += 36

            if b"\0" not in raw_name:
                raise ValueError("Unterminated Apple property name")

            name = raw_name.split(b"\0", 1)[0].decode("ascii")

            if name in names:
                raise ValueError(f"Duplicate Apple property: {name}")

            if pos + align4(length) > len(data):
                raise ValueError("Property value exceeds Apple DT")

            value = data[pos:pos + length]
            pos += align4(length)

            names.add(name)
            property_count += 1

            if name == "name":
                if not value.endswith(b"\0"):
                    raise ValueError("Node name is not NUL terminated")

                node_name = value[:-1].decode("utf-8", "strict")

        if node_name is None:
            raise ValueError("Node without name property")

        for _ in range(nchildren):
            parse()

        return node_name

    root_name = parse()

    if pos != len(data):
        raise ValueError("Unexpected trailing bytes in Apple DT")

    return {
        "root": root_name,
        "nodes": node_count,
        "properties": property_count,
        "bytes": len(data)
    }


def main():
    parser = argparse.ArgumentParser(
        description="Linux FDT to Apple Device Tree converter"
    )

    parser.add_argument("input", help="Input Linux DTB")

    parser.add_argument(
        "-o", "--output",
        default="obsidian-live.adt",
        help="Output Apple DT file"
    )

    args = parser.parse_args()

    source = Path(args.input)
    destination = Path(args.output)

    if not source.is_file():
        raise FileNotFoundError(f"Input file not found: {source}")

    if source.resolve() == destination.resolve():
        raise ValueError("Input and output paths must be different")

    blob = source.read_bytes()

    print("[1/4] Parsing Linux FDT...")
    root, fdt_info = parse_fdt(blob)

    print("[2/4] Preparing Apple Device Tree...")
    rename_map = {}

    apple_tree = prepare_tree(
        root,
        is_root=True,
        rename_map=rename_map
    )

    print("[3/4] Serializing and validating...")
    result = serialize_node(apple_tree)
    validation = validate_apple_tree(result)

    print("[4/4] Writing output...")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(result)

    report = {
        "status": "conversion and structural validation successful",
        "input": str(source),
        "output": str(destination),
        "input_bytes": len(blob),
        "fdt": fdt_info,
        "apple_dt": validation,
        "renamed_count": len(rename_map),
        "renamed_properties": rename_map,
        "warnings": [
            "Long property names were shortened. Drivers expecting original names will not find these aliases.",
            "FDT reserve map entries were reported but not converted into Apple DT properties.",
            "Structural validation does not prove XNU boot compatibility."
        ]
    }

    report_path = destination.with_suffix(".json")

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\nCONVERSION SUCCESSFUL")
    print(f"Apple DT: {destination}")
    print(f"Report: {report_path}")
    print(f"Nodes: {validation['nodes']}")
    print(f"Properties: {validation['properties']}")
    print(f"Renamed properties: {len(rename_map)}")
    print(f"Reserve map entries: {fdt_info['reserve_entry_count']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
