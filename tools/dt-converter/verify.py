
import json
import struct
import sys
from pathlib import Path

from convert import parse_fdt


def parse_apple_dt(data):
    pos = 0
    nodes = {}

    def parse(path=""):
        nonlocal pos

        if pos + 8 > len(data):
            raise ValueError("Truncated node")

        nprops, nchildren = struct.unpack_from("<II", data, pos)
        pos += 8

        props = {}
        node_name = None

        for _ in range(nprops):
            if pos + 36 > len(data):
                raise ValueError("Truncated property")

            raw_name = data[pos:pos + 32]
            length = struct.unpack_from("<I", data, pos + 32)[0]
            pos += 36

            name = raw_name.split(b"\0", 1)[0].decode("ascii")
            value = data[pos:pos + length]
            pos += (length + 3) & ~3

            props[name] = value

            if name == "name":
                node_name = value[:-1].decode("utf-8")

        if node_name is None:
            raise ValueError("Missing node name")

        current_path = path + "/" + node_name

        if current_path in nodes:
            raise ValueError(f"Duplicate node path: {current_path}")

        nodes[current_path] = props

        for _ in range(nchildren):
            parse(current_path)

    parse()

    if pos != len(data):
        raise ValueError("Unexpected trailing data")

    return nodes


def collect_fdt_nodes(root):
    result = {}

    def walk(node, path=""):
        name = "device-tree" if not path else node["source_name"]
        current = path + "/" + name

        result[current] = dict(node["props"])

        for child in node["children"]:
            walk(child, current)

    walk(root)
    return result


def main():
    base = Path(__file__).parent

    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\platform-tools\obsidian-live.dtb"
    )

    apple_file = base / "obsidian-live.adt"
    report_file = base / "obsidian-live.json"

    print("[1/4] Loading source DTB...")
    root, _ = parse_fdt(source.read_bytes())

    print("[2/4] Loading converted Apple DT...")
    apple_nodes = parse_apple_dt(apple_file.read_bytes())

    report = json.loads(report_file.read_text(encoding="utf-8"))
    rename_map = report["renamed_properties"]

    print("[3/4] Comparing nodes and properties...")
    fdt_nodes = collect_fdt_nodes(root)

    missing_nodes = []
    extra_nodes = []
    missing_properties = []
    extra_properties = []
    changed_properties = []

    if set(fdt_nodes) != set(apple_nodes):
        missing_nodes = sorted(set(fdt_nodes) - set(apple_nodes))
        extra_nodes = sorted(set(apple_nodes) - set(fdt_nodes))

    for path, source_props in fdt_nodes.items():
        target_props = apple_nodes.get(path)

        if target_props is None:
            continue

        expected = {}

        for name, value in source_props.items():
            if name == "name":
                continue

            alias = rename_map.get(path + ":" + name, name)
            expected[alias] = (name, value)

        actual_names = set(target_props) - {"name"}
        expected_names = set(expected)

        for name in sorted(expected_names - actual_names):
            original, _ = expected[name]
            missing_properties.append(f"{path}: {original}")

        for name in sorted(actual_names - expected_names):
            extra_properties.append(f"{path}: {name}")

        for name in sorted(expected_names & actual_names):
            original, expected_value = expected[name]
            actual_value = target_props[name]

            if expected_value != actual_value:
                changed_properties.append(
                    f"{path}: {original}"
                )

    print("[4/4] Results")

    print(f"Source nodes: {len(fdt_nodes)}")
    print(f"Apple nodes: {len(apple_nodes)}")
    print(f"Missing nodes: {len(missing_nodes)}")
    print(f"Extra nodes: {len(extra_nodes)}")
    print(f"Missing properties: {len(missing_properties)}")
    print(f"Extra properties: {len(extra_properties)}")
    print(f"Changed values: {len(changed_properties)}")

    if any((
        missing_nodes,
        extra_nodes,
        missing_properties,
        extra_properties,
        changed_properties
    )):
        print("\nVERIFICATION FAILED")

        for title, items in (
            ("Missing nodes", missing_nodes),
            ("Extra nodes", extra_nodes),
            ("Missing properties", missing_properties),
            ("Extra properties", extra_properties),
            ("Changed values", changed_properties)
        ):
            if items:
                print(f"\n{title}:")
                for item in items[:20]:
                    print("  " + item)

        sys.exit(1)

    print("\nVERIFICATION PASSED")
    print("All converted node paths and property values match.")


if __name__ == "__main__":
    main()
