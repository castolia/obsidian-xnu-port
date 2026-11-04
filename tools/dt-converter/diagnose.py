from pathlib import Path
from convert import parse_fdt

source = Path(r"C:\platform-tools\obsidian-live.dtb")
root, info = parse_fdt(source.read_bytes())

long_names = []

def walk(node, path=""):
    name = node["source_name"]
    current = path + "/" + name

    for prop_name, value in node["props"]:
        length = len(prop_name.encode("utf-8"))

        if length > 31:
            long_names.append((current, prop_name, length))

    for child in node["children"]:
        walk(child, current)

walk(root)

print("Total incompatible property names:", len(long_names))

for path, name, length in long_names:
    print(f"\nNode: {path}")
    print(f"Property: {name}")
    print(f"Length: {length} bytes")