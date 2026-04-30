"""
Compute evaluation metrics for binary point cloud change detection.

We consider two types of prediction outputs:

1. Full-resolution predictions:
   Methods that produce one prediction per input point (e.g., C2C, M3C2, Siamese KPConv, EF-Siamese KPConv, PGN3DCD).

2. Non full-resolution predictions:
   Methods that produce predictions on a subset of points (e.g., F2S3, Landslide-3D).
   These predictions are first mapped to the full-resolution point cloud via nearest-neighbor interpolation.

Supports two evaluation protocols:
1. Dual-direction (symmetric nearest neighbor matching)
2. Classical (one-to-one correspondence)

Metrics:
- Precision, Recall, F1-score
- mAcc, mIoU
- Per-class Accuracy and IoU

Labels:
- 0: unchanged
- 1: changed
"""

import numpy as np
import argparse
import os
import os.path as osp
from scipy.spatial import cKDTree
from plyfile import PlyData, PlyElement


def get_full_resolution_output(points_gt, points_pred, pred_labels_sparse, threshold=None):
    """
    Map sparse predictions to full-resolution GT points via nearest neighbor.
    """
    if len(points_pred) == 0:
        raise ValueError("pred_points is empty!")
    if len(points_gt) == 0:
        raise ValueError("gt_points is empty!")

    tree_pred = cKDTree(points_pred)
    dist, idx = tree_pred.query(points_gt, k=1, workers=-1)

    pred_labels_full = pred_labels_sparse[idx]

    if threshold is not None and threshold > 0:
        far_mask = dist > threshold
        pred_labels_full[far_mask] = 0
    return pred_labels_full


def dual_direction_metrics(gt_points, gt_labels, pred_points, pred_labels):
    """Compute dual-direction metrics using nearest neighbor matching."""
    if len(gt_points) == 0 or len(pred_points) == 0:
        raise ValueError("GT or Pred points are empty!")

    # GT -> Pred (Recall)
    tree_pred = cKDTree(pred_points)
    _, idx_pred = tree_pred.query(gt_points, k=1, workers=-1)
    TP_gt = np.sum((gt_labels == 1) & (pred_labels[idx_pred] == 1))
    FN_gt = np.sum((gt_labels == 1) & (pred_labels[idx_pred] == 0))

    # Pred -> GT (Precision)
    tree_gt = cKDTree(gt_points)
    _, idx_gt = tree_gt.query(pred_points, k=1, workers=-1)
    TP_pred = np.sum((pred_labels == 1) & (gt_labels[idx_gt] == 1))
    FP_pred = np.sum((pred_labels == 1) & (gt_labels[idx_gt] == 0))

    # Symmetric TP
    TP = min(TP_gt, TP_pred)
    FN = FN_gt
    FP = FP_pred
    TN = np.sum(gt_labels == 0) - FP  # TN for unchanged class

    # Compute metrics
    precision = TP / (TP + FP + 1e-8)
    recall = TP / (TP + FN + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)
    iou = TP / (TP + FP + FN + 1e-8)

    # mAcc/mIoU
    acc_changed = recall
    acc_unchanged = TN / (TN + FP + 1e-8)
    mAcc = 0.5 * (acc_changed + acc_unchanged)

    iou_changed = iou
    iou_unchanged = TN / (TN + FP + FN + 1e-8)
    mIoU = 0.5 * (iou_changed + iou_unchanged)

    overall_acc = (TP + TN) / (TP + TN + FP + FN + 1e-8)

    return precision, recall, f1, mAcc, mIoU, (acc_unchanged, acc_changed), (iou_unchanged, iou_changed), overall_acc, TP, TN, FP, FN

def classical_metrics(gt_labels, pred_labels):
    """Compute classical metrics assuming one-to-one correspondence."""
    TP = np.sum((gt_labels == 1) & (pred_labels == 1))
    FN = np.sum((gt_labels == 1) & (pred_labels == 0))
    TN = np.sum((gt_labels == 0) & (pred_labels == 0))
    FP = np.sum((gt_labels == 0) & (pred_labels == 1))

    precision = TP / (TP + FP + 1e-8)
    recall = TP / (TP + FN + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)

    acc_changed = recall
    acc_unchanged = TN / (TN + FP + 1e-8)
    mAcc = 0.5 * (acc_changed + acc_unchanged)

    iou_changed = TP / (TP + FP + FN + 1e-8)
    iou_unchanged = TN / (TN + FP + FN + 1e-8)
    mIoU = 0.5 * (iou_changed + iou_unchanged)

    overall_acc = (TP + TN) / (TP + TN + FP + FN + 1e-8)

    return precision, recall, f1, mAcc, mIoU, (acc_unchanged, acc_changed), (iou_unchanged, iou_changed), overall_acc, TP, TN, FP, FN

def load_pred_data(pred_file):
    data = np.loadtxt(pred_file)
    gt_labels = data[:, 3].astype(int)
    # Distance column depends on method
    if "C2C" in pred_file or "c2c" in pred_file:
        est_distances = data[:, 4]
    elif "M3C2" in pred_file or "m3c2" in pred_file:
        est_distances = data[:, 6]
    else:
        raise ValueError("Unknown method in pred_data filename")
    points_xyz = data[:, :3]
    return points_xyz, gt_labels, est_distances


def read_from_ply(filename, name_feat="pred"):
    """read XYZ for each vertex."""
    assert os.path.isfile(filename)
    with open(filename, "rb") as f:
        plydata = PlyData.read(f)
        x = plydata.elements[0].data["x"]
        x = x.reshape(-1, 1)
        y = plydata.elements[0].data["y"]
        y = y.reshape(-1, 1)
        z = plydata.elements[0].data["z"]
        z = z.reshape(-1, 1)
        # r = plydata.elements[0].data["red"]
        # r = r.reshape(-1, 1)
        # g = plydata.elements[0].data["green"]
        # g = g.reshape(-1, 1)
        # b = plydata.elements[0].data["blue"]
        # b = b.reshape(-1, 1)
        # cd_type = plydata.elements[0].data["scalar_cd_type"]
        cd_type = plydata.elements[0].data[name_feat]
        cd_type = cd_type.reshape(-1, 1)
        vertices = np.concatenate((x,y,z, cd_type), axis=1)

    return vertices

def main():
    parser = argparse.ArgumentParser(description="Compute mAcc and mIoU for change detection")
    parser.add_argument("--input_data",
                        default="path/to/gt.ply",
                        help="Path to ground-truth point cloud (PLY)")

    parser.add_argument("--pred_data",
                        default="path/to/pred.ply",
                        help="Prediction file (PLY or TXT)")

    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Distance threshold for binary classification (dataset-dependent)")
    args = parser.parse_args()

    output_file = args.pred_data.replace("inputs", "outputs").replace(".ply", f"_metrics_thr_{args.threshold:.4f}.txt")
    os.makedirs(osp.dirname(output_file), exist_ok=True)

    method_name = osp.splitext(osp.basename(args.pred_data))[0]
    pred_name = method_name.lower()

    # Load GT
    data_gt = read_from_ply(args.input_data, name_feat="scalar_cd_type")
    points_gt, labels_gt = data_gt[:, :3], data_gt[:, 3].astype(int)

    # Load prediction
    if args.pred_data.endswith(".txt"):
        points_pred, _, est_distances = load_pred_data(args.pred_data)
        pred_labels = (np.abs(est_distances) > args.threshold).astype(int)

    elif any(k in pred_name for k in ["c2c", "m3c2", "f2s3", "landslide3d"]):
        if "c2c" in pred_name:
            data_pred = read_from_ply(args.pred_data, name_feat="scalar_C2C_absolute_distances")
        elif "m3c2" in pred_name:
            data_pred = read_from_ply(args.pred_data, name_feat="scalar_M3C2_distance")
        else:
            data_pred = read_from_ply(args.pred_data, name_feat="scalar_Scalar_field")

        points_pred, est_distances = data_pred[:, :3], np.abs(data_pred[:, 3])
        pred_labels_sparse = (est_distances > args.threshold).astype(int)

        # sparse → full
        pred_labels = get_full_resolution_output(points_gt, points_pred, pred_labels_sparse)
        points_pred = points_gt

    elif any(k in pred_name for k in ["kpconv", "pgn3dcd"]):
        data_pred = read_from_ply(args.pred_data, name_feat="pred")
        points_pred, pred_labels = data_pred[:, :3], data_pred[:, 3]
        pred_labels = (pred_labels >= 0.5).astype(int)

    else:
        raise ValueError("Unsupported method type")

    # Metrics
    dd_metrics = dual_direction_metrics(points_gt, labels_gt, points_pred, pred_labels)
    cl_metrics = classical_metrics(labels_gt, pred_labels)

    precision_dd, recall_dd, f1_dd, mAcc_dd, mIoU_dd, accs_dd, ious_dd, overall_acc_dd, TP_dd, TN_dd, FP_dd, FN_dd = dd_metrics
    precision_cl, recall_cl, f1_cl, mAcc_cl, mIoU_cl, accs_cl, ious_cl, overall_acc_cl, TP_cl, TN_cl, FP_cl, FN_cl = cl_metrics

    # Save binary results
    data_pred_binary = np.concatenate((points_pred, pred_labels.reshape(-1, 1)), axis=1)
    save_dir = osp.join(osp.dirname(args.pred_data).replace("inputs", "outputs"), "binary_results")
    os.makedirs(save_dir, exist_ok=True)

    filename = method_name + f"_binary_thr_{args.threshold:.4f}.txt"
    np.savetxt(osp.join(save_dir, filename), data_pred_binary, fmt="%.6f %.6f %.6f %d")

    # Save metrics
    with open(output_file, "w") as f:
        f.write(f"Method: {method_name}\nThreshold: {args.threshold:.4f}\n\n")
        f.write(
            f"GT changed: {np.sum(labels_gt == 1)}, GT unchanged: {np.sum(labels_gt == 0)}, Total GT: {len(labels_gt)}\n")
        f.write(f"Pred points: {len(pred_labels)}\n\n")

        f.write("=== Dual-direction metrics ===\n")
        f.write("Precision, Recall, F1-score, Overall Accuracy, mAcc, mIoU\n")
        f.write(
            f"{precision_dd:.4f} {recall_dd:.4f} {f1_dd:.4f} {overall_acc_dd:.4f} {mAcc_dd:.4f} {mIoU_dd:.4f}\n")
        f.write(f"Accuracy per class (unchanged, changed): {accs_dd}\n")
        f.write(f"IoU per class (unchanged, changed): {ious_dd}\n")
        f.write(f"TP: {TP_dd}, TN: {TN_dd}, FP: {FP_dd}, FN: {FN_dd}\n\n")

        f.write("=== Classical metrics ===\n")
        f.write(
            f"Precision: {precision_cl:.4f}, Recall: {recall_cl:.4f}, F1: {f1_cl:.4f}, mAcc: {mAcc_cl:.4f}, mIoU: {mIoU_cl:.4f}\n")
        f.write(f"Accuracy per class (unchanged, changed): {accs_cl}\n")
        f.write(f"IoU per class (unchanged, changed): {ious_cl}\n")
        f.write(f"Overall Accuracy: {overall_acc_cl:.4f}\n")
        f.write(f"TP: {TP_cl}, TN: {TN_cl}, FP: {FP_cl}, FN: {FN_cl}\n")

    print(f"Results saved to {output_file}")
    print("=== Dual-direction metrics ===")
    print(
        f"Precision: {precision_dd:.4f}, Recall: {recall_dd:.4f}, F1: {f1_dd:.4f}, mAcc: {mAcc_dd:.4f}, mIoU: {mIoU_dd:.4f}, Overall Acc: {overall_acc_dd:.4f}")
    print("=== Classical metrics ===")
    print(
        f"Precision: {precision_cl:.4f}, Recall: {recall_cl:.4f}, F1: {f1_cl:.4f}, mAcc: {mAcc_cl:.4f}, mIoU: {mIoU_cl:.4f}, Overall Acc: {overall_acc_cl:.4f}")


if __name__ == "__main__":
    main()
