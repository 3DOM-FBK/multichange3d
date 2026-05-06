"""
Generate labeled point cloud pairs for binary change detection.

This script merges "unchanged" and "changed" point clouds into a unified format
with binary labels:

- 0: unchanged
- 1: changed

Supports flexible PLY inputs:
- xyz + RGB
- xyz + intensity
- xyz only (fallback to fake RGB)

Outputs:
- pointCloud0.ply
- pointCloud1.ply

Each output contains:
- xyz + (rgb or intensity) + cd_type

"""

import numpy as np
import os
import os.path as osp
import argparse
from plyfile import PlyData, PlyElement


def read_ply_points_flexible(ply_path):
    """
    Read PLY with flexible attributes:
    - xyz + RGB
    - xyz + intensity
    - xyz only

    Returns:
        dict with keys: xyz, rgb, intensity
    """
    ply = PlyData.read(ply_path)
    v = ply.elements[0].data
    names = v.dtype.names

    if not {"x", "y", "z"} <= set(names):
        raise ValueError(f"{ply_path} missing xyz fields")

    xyz = np.vstack([v["x"], v["y"], v["z"]]).T.astype(np.float32)

    rgb, intensity = None, None

    # RGB
    if {"red", "green", "blue"} <= set(names):
        rgb = np.vstack([v["red"], v["green"], v["blue"]]).T.astype(np.float32)
    elif {"r", "g", "b"} <= set(names):
        rgb = np.vstack([v["r"], v["g"], v["b"]]).T.astype(np.float32)

    # intensity
    for n in names:
        if "intensity" in n.lower():
            intensity = np.asarray(v[n]).astype(np.float32)
            break

    # fallback
    if rgb is None and intensity is None:
        rgb = np.zeros((xyz.shape[0], 3), dtype=np.float32)

    return {"xyz": xyz, "rgb": rgb, "intensity": intensity}


def write_ply_auto(save_path, xyz, rgb=None, intensity=None, feat=None, name_feat="cd_type"):
    """
    Write PLY with adaptive attributes.
    """
    num_verts = xyz.shape[0]

    dtype_list = [("x", "f4"), ("y", "f4"), ("z", "f4")]

    if intensity is not None:
        dtype_list.append(("intensity", "f4"))

    if rgb is not None:
        dtype_list += [("red", "u1"), ("green", "u1"), ("blue", "u1")]

    if feat is not None:
        dtype_list.append((name_feat, "f4"))

    vertex_data = np.empty(num_verts, dtype=dtype_list)

    vertex_data["x"], vertex_data["y"], vertex_data["z"] = xyz.T

    if intensity is not None:
        vertex_data["intensity"] = intensity.astype(np.float32)

    if rgb is not None:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        vertex_data["red"], vertex_data["green"], vertex_data["blue"] = rgb.T

    if feat is not None:
        vertex_data[name_feat] = feat.astype(np.float32)

    el = PlyElement.describe(vertex_data, "vertex")
    PlyData([el], text=False).write(save_path)

    print(f"Saved {num_verts} points → {save_path}")


def load_and_label(path, label):
    """Load point cloud and assign binary label."""
    data = read_ply_points_flexible(path)
    xyz = data["xyz"]
    feat = np.full((xyz.shape[0], 1), label, dtype=np.float32)
    return data, feat


def concat_data(d1, f1, d2, f2):
    """Concatenate unchanged and changed point clouds."""
    xyz = np.vstack([d1["xyz"], d2["xyz"]])
    feat = np.vstack([f1, f2]).flatten()

    rgb = None
    intensity = None

    if d1["rgb"] is not None and d2["rgb"] is not None:
        rgb = np.vstack([d1["rgb"], d2["rgb"]])

    if d1["intensity"] is not None and d2["intensity"] is not None:
        intensity = np.concatenate([d1["intensity"], d2["intensity"]])

    return xyz, rgb, intensity, feat


def main():
    parser = argparse.ArgumentParser(description="Generate binary labeled point cloud pairs")

    parser.add_argument("--input_dir",
                        default="path/to/scene",
                        help="Directory containing input PLY files")

    args = parser.parse_args()
    scene_dir = args.input_dir

    # Default file structure (can extend later)
    files = {
        "unchanged_0": "morning_unchanged.ply",
        "changed_0":   "morning_changed.ply",
        "unchanged_1": "afternoon_unchanged.ply",
        "changed_1":   "afternoon_changed.ply",
    }

    # Load
    d_u0, f_u0 = load_and_label(osp.join(scene_dir, files["unchanged_0"]), 0)
    d_c0, f_c0 = load_and_label(osp.join(scene_dir, files["changed_0"]), 1)
    d_u1, f_u1 = load_and_label(osp.join(scene_dir, files["unchanged_1"]), 0)
    d_c1, f_c1 = load_and_label(osp.join(scene_dir, files["changed_1"]), 1)

    # Merge
    xyz0, rgb0, intensity0, feat0 = concat_data(d_u0, f_u0, d_c0, f_c0)
    xyz1, rgb1, intensity1, feat1 = concat_data(d_u1, f_u1, d_c1, f_c1)

    # Save
    save_dir = scene_dir.replace("inputs", "outputs")
    os.makedirs(save_dir, exist_ok=True)

    write_ply_auto(osp.join(save_dir, "pointCloud0.ply"), xyz0, rgb0, intensity0, feat0)
    write_ply_auto(osp.join(save_dir, "pointCloud1.ply"), xyz1, rgb1, intensity1, feat1)

    print("Done writing both point clouds.")


if __name__ == "__main__":
    main()
