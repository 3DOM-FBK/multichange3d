"""
Estimate point cloud spacing using k-NN search.

This script computes the mean and median point spacing for each point cloud file
in a given directory. It supports both `.ply` and `.txt` formats.

For `.ply` files:
- XYZ coordinates are extracted using plyfile (robust to field naming)

For `.txt` files:
- Assumes XYZ are stored in the first three columns

Output:
- Per-file statistics (number of points, mean spacing, median spacing, runtime)
- Summary statistics across all files

"""

import open3d as o3d
import numpy as np
import os
import os.path as osp
import time
import argparse
from plyfile import PlyData


def read_from_ply(filename):
    """
    Robustly read XYZ from PLY using plyfile.
    Supports arbitrary capitalization of x/y/z.
    """
    assert os.path.isfile(filename), f"{filename} not found"

    with open(filename, "rb") as f:
        plydata = PlyData.read(f)

        elem = None
        for el in plydata.elements:
            names = el.data.dtype.names
            low_names = [n.lower() for n in names]
            if {"x", "y", "z"} <= set(low_names):
                elem = el
                break

        if elem is None:
            raise ValueError(f"No vertex element with x/y/z found in {filename}")

        names = elem.data.dtype.names

        def pick(field):
            for n in names:
                if n.lower() == field:
                    return n
            return None

        x = np.asarray(elem.data[pick("x")]).reshape(-1, 1)
        y = np.asarray(elem.data[pick("y")]).reshape(-1, 1)
        z = np.asarray(elem.data[pick("z")]).reshape(-1, 1)

    return np.hstack((x, y, z)).astype(np.float32)


def estimate_point_spacing(pcd, k=6):
    """Estimate mean and median point spacing using k-NN."""
    tree = o3d.geometry.KDTreeFlann(pcd)
    distances = []

    for i in range(len(pcd.points)):
        _, _, dists = tree.search_knn_vector_3d(pcd.points[i], k)
        if len(dists) > 1:
            nn_dists = np.sqrt(dists[1:])  # exclude self
            distances.append(np.mean(nn_dists))

    distances = np.array(distances)

    return {
        "mean": float(np.mean(distances)),
        "median": float(np.median(distances))
    }


def main():
    parser = argparse.ArgumentParser(description="Estimate point cloud spacing")

    parser.add_argument("--input_dir",
                        default="path/to/pointclouds",
                        help="Directory containing .ply or .txt files")

    args = parser.parse_args()
    path_pcd = args.input_dir

    assert os.path.isdir(path_pcd), f"{path_pcd} not found"

    output_txt = osp.join(path_pcd, "spacing_summary.txt")

    ply_files = sorted([f for f in os.listdir(path_pcd) if f.endswith(".ply")])
    txt_files = sorted([f for f in os.listdir(path_pcd) if f.endswith(".txt")])

    files = ply_files if ply_files else txt_files

    if not files:
        print("No .ply or .txt files found.")
        return

    results = []
    total_start = time.time()

    for name in files:
        path = osp.join(path_pcd, name)
        print(f"Processing: {name}")
        start_time = time.time()

        try:
            if name.endswith(".ply"):
                points = read_from_ply(path)
            elif name.endswith(".txt"):
                points = np.loadtxt(path)[:, :3]
            else:
                raise ValueError("Unsupported file format")

            num_points = points.shape[0]
            if num_points == 0:
                print(f"⚠️ Empty point cloud: {name}")
                continue

            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))

            spacing = estimate_point_spacing(pcd)
            elapsed = time.time() - start_time

            results.append((name, num_points, spacing["mean"], spacing["median"], elapsed))

            print(f"  Points: {num_points}, Mean: {spacing['mean']:.4f}, "
                  f"Median: {spacing['median']:.4f}, Time: {elapsed:.2f}s")

        except Exception as e:
            print(f"Error processing {name}: {e}")

    # ===== Summary =====
    if results:
        mean_all = np.mean([r[2] for r in results])
        median_all = np.mean([r[3] for r in results])
        avg_time = np.mean([r[4] for r in results])
        total_time = time.time() - total_start
        avg_points = np.mean([r[1] for r in results])

        with open(output_txt, "w") as f:
            f.write("Filename\tNumPoints\tMeanSpacing\tMedianSpacing\tTime(s)\n")
            for r in results:
                f.write(f"{r[0]}\t{r[1]}\t{r[2]:.6f}\t{r[3]:.6f}\t{r[4]:.2f}\n")

            f.write("\nSummary:\n")
            f.write(f"AveragePoints={avg_points:.2f}\n")
            f.write(f"MeanSpacing={mean_all:.6f}\n")
            f.write(f"MedianSpacing={median_all:.6f}\n")
            f.write(f"AverageTimePerFile={avg_time:.2f}s\n")
            f.write(f"TotalTime={total_time:.2f}s\n")

        print(f"\nResults saved to: {output_txt}")
        print(f"Average Points: {avg_points:.0f}, Mean={mean_all:.4f}, Median={median_all:.4f}")
        print(f"Avg time/file: {avg_time:.2f}s, Total: {total_time:.2f}s")

    else:
        print("No valid point clouds processed.")


if __name__ == "__main__":
    main()
