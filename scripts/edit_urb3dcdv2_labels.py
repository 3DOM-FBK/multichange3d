"""
Convert multi-class point cloud labels into binary change labels.

This script converts input labels into binary classes for fair comparison:

- 0: unchanged
- 1: changed

The input PLY is expected to contain a change-related label field
(e.g., `label_ch`). The output PLY will contain a binary label field `cd_type`.

"""

import numpy as np
import argparse
import os
import os.path as osp
from plyfile import PlyData, PlyElement


# Label definition
UNCHANGED = 0
CHANGED = 1


def read_ply_with_label(filename):
    """Read PLY file and extract XYZ, RGB, and change label."""
    assert os.path.isfile(filename), f"{filename} not found"

    with open(filename, "rb") as f:
        plydata = PlyData.read(f)
        vertex = plydata.elements[0].data

        x = vertex["x"].reshape(-1, 1)
        y = vertex["y"].reshape(-1, 1)
        z = vertex["z"].reshape(-1, 1)

        # RGB (optional but expected)
        r = vertex["red"].reshape(-1, 1)
        g = vertex["green"].reshape(-1, 1)
        b = vertex["blue"].reshape(-1, 1)

        # label field (robust check)
        if "label_ch" in vertex.dtype.names:
            label = vertex["label_ch"].reshape(-1, 1)
        elif "scalar_cd_type" in vertex.dtype.names:
            label = vertex["scalar_cd_type"].reshape(-1, 1)
        else:
            raise KeyError("No valid label field found (expected 'label_ch' or 'scalar_cd_type').")

    return x, y, z, r, g, b, label


def convert_to_binary(label):
    """Convert multi-class labels to binary."""
    label_bin = np.zeros_like(label)
    label_bin[label > 0.5] = CHANGED
    label_bin[label <= 0.5] = UNCHANGED
    return label_bin


def save_ply(filename, x, y, z, r, g, b, label):
    """Save processed PLY with binary labels."""
    vertices = np.concatenate((x, y, z, r, g, b, label), axis=1)

    vertex_all = np.array(
        [tuple(v) for v in vertices],
        dtype=[
            ("x", "f4"),
            ("y", "f4"),
            ("z", "f4"),
            ("red", "u1"),
            ("green", "u1"),
            ("blue", "u1"),
            ("cd_type", "u1"),
        ],
    )

    el = PlyElement.describe(vertex_all, "vertex")
    PlyData([el], text=False).write(filename)


def main():
    parser = argparse.ArgumentParser(description="Convert multi-class labels to binary change labels")

    parser.add_argument("--input_data",
                        default="path/to/input.ply",
                        help="Input PLY file")

    parser.add_argument("--output_data",
                        default=None,
                        help="Output PLY file (default: auto-generated)")

    args = parser.parse_args()

    if args.output_data is None:
        output_path = args.input_data.replace(".ply", "_binary.ply")
    else:
        output_path = args.output_data

    os.makedirs(osp.dirname(output_path), exist_ok=True)

    # Load
    x, y, z, r, g, b, label = read_ply_with_label(args.input_data)

    # Convert
    label_bin = convert_to_binary(label)

    # Save
    save_ply(output_path, x, y, z, r, g, b, label_bin)

    print(f"Saved binary PLY to {output_path}")


if __name__ == "__main__":
    main()
