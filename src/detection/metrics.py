"""
Segmentation Evaluation Metrics & Confusion Matrix Engine.

Calculates:
- Per-class IoU (Jaccard Index)
- Mean IoU (macro-averaged over active classes)
- Per-class and macro Precision, Recall, and F1-score
- Overall Pixel Accuracy
- Complete Confusion Matrix (rows = Ground Truth, columns = Predicted)
- MANDATORY Specific Confusion Tracking:
  * OIL -> LOOK-ALIKE confusion (missed oil mistaken for look-alikes)
  * LOOK-ALIKE -> OIL confusion (false alarms: look-alikes mistaken for oil)
  * Look-alike Rejection Rate
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import torch

from src.detection.dataset_adapters import KRESTENITIS_CLASSES


def compute_confusion_matrix(
    pred_mask: Union[np.ndarray, torch.Tensor],
    true_mask: Union[np.ndarray, torch.Tensor],
    num_classes: int = 4,
) -> np.ndarray:
    """
    Compute C x C confusion matrix where rows are True classes and cols are Predicted classes.
    
    Args:
        pred_mask: 2D or 1D array of predicted class indices.
        true_mask: 2D or 1D array of ground truth class indices.
        num_classes: Number of distinct classes.
        
    Returns:
        num_classes x num_classes integer confusion matrix.
    """
    if isinstance(pred_mask, torch.Tensor):
        pred_mask = pred_mask.detach().cpu().numpy()
    if isinstance(true_mask, torch.Tensor):
        true_mask = true_mask.detach().cpu().numpy()
        
    p = pred_mask.ravel().astype(np.int64)
    t = true_mask.ravel().astype(np.int64)
    
    # Filter valid indices within [0, num_classes - 1]
    valid = (t >= 0) & (t < num_classes) & (p >= 0) & (p < num_classes)
    p_valid = p[valid]
    t_valid = t[valid]
    
    # Fast 2D bincount
    indices = t_valid * num_classes + p_valid
    cm = np.bincount(indices, minlength=num_classes * num_classes).reshape(num_classes, num_classes)
    return cm


def evaluate_segmentation_metrics(
    confusion_matrix: np.ndarray,
    class_names: Optional[Dict[int, str]] = None,
    oil_class_id: int = 1,
    lookalike_class_id: int = 2,
) -> Dict[str, Any]:
    """
    Calculate comprehensive segmentation metrics from an accumulated confusion matrix.
    
    Args:
        confusion_matrix: C x C confusion matrix (rows = True, cols = Pred).
        class_names: Optional mapping from class ID to human-readable string.
        oil_class_id: Integer index for Oil class (default: 1).
        lookalike_class_id: Integer index for Look-alike class (default: 2).
        
    Returns:
        Structured dictionary with per-class and aggregate metrics.
    """
    cm = confusion_matrix.astype(np.float64)
    num_classes = cm.shape[0]
    names = class_names or {i: f"Class_{i}" for i in range(num_classes)}
    
    total_pixels = float(np.sum(cm))
    tp = np.diag(cm)
    fp = np.sum(cm, axis=0) - tp
    fn = np.sum(cm, axis=1) - tp
    tn = total_pixels - (tp + fp + fn)
    support = np.sum(cm, axis=1)
    
    # Pixel Accuracy
    pixel_accuracy = float(np.sum(tp) / total_pixels) if total_pixels > 0 else 0.0
    
    # Per-class IoU, Precision, Recall, F1
    per_class_iou: Dict[str, float] = {}
    per_class_precision: Dict[str, float] = {}
    per_class_recall: Dict[str, float] = {}
    per_class_f1: Dict[str, float] = {}
    per_class_support: Dict[str, int] = {}
    
    for i in range(num_classes):
        cname = names.get(i, f"Class_{i}")
        denom_iou = tp[i] + fp[i] + fn[i]
        denom_prec = tp[i] + fp[i]
        denom_rec = tp[i] + fn[i]
        
        iou = float(tp[i] / denom_iou) if denom_iou > 0 else 0.0
        prec = float(tp[i] / denom_prec) if denom_prec > 0 else 0.0
        rec = float(tp[i] / denom_rec) if denom_rec > 0 else 0.0
        f1 = float(2.0 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        
        per_class_iou[cname] = round(iou, 4)
        per_class_precision[cname] = round(prec, 4)
        per_class_recall[cname] = round(rec, 4)
        per_class_f1[cname] = round(f1, 4)
        per_class_support[cname] = int(support[i])
        
    # Mean IoU and Macro F1 (excluding classes with 0 support)
    active_classes = [i for i in range(num_classes) if support[i] > 0]
    mean_iou = float(np.mean([per_class_iou[names[i]] for i in active_classes])) if active_classes else 0.0
    macro_f1 = float(np.mean([per_class_f1[names[i]] for i in active_classes])) if active_classes else 0.0
    macro_precision = float(np.mean([per_class_precision[names[i]] for i in active_classes])) if active_classes else 0.0
    macro_recall = float(np.mean([per_class_recall[names[i]] for i in active_classes])) if active_classes else 0.0
    
    # MANDATORY Specific Confusion Tracking
    # 1. Oil -> Look-alike confusion: True Oil predicted as Look-alike
    true_oil_total = support[oil_class_id]
    oil_to_lookalike_count = int(cm[oil_class_id, lookalike_class_id])
    oil_to_lookalike_rate = float(oil_to_lookalike_count / true_oil_total) if true_oil_total > 0 else 0.0
    
    # 2. Look-alike -> Oil confusion: True Look-alike predicted as Oil
    true_lookalike_total = support[lookalike_class_id]
    lookalike_to_oil_count = int(cm[lookalike_class_id, oil_class_id])
    lookalike_to_oil_rate = float(lookalike_to_oil_count / true_lookalike_total) if true_lookalike_total > 0 else 0.0
    
    # 3. Look-alike Rejection Rate: 1.0 - Lookalike-to-oil rate
    lookalike_rejection_rate = 1.0 - lookalike_to_oil_rate
    
    return {
        "overall_pixel_accuracy": round(pixel_accuracy, 4),
        "mean_iou": round(mean_iou, 4),
        "macro_f1": round(macro_f1, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "per_class_iou": per_class_iou,
        "per_class_precision": per_class_precision,
        "per_class_recall": per_class_recall,
        "per_class_f1": per_class_f1,
        "per_class_support": per_class_support,
        "mandatory_oil_lookalike_analysis": {
            "oil_to_lookalike_pixels": oil_to_lookalike_count,
            "oil_to_lookalike_rate": round(oil_to_lookalike_rate, 4),
            "lookalike_to_oil_pixels": lookalike_to_oil_count,
            "lookalike_to_oil_rate": round(lookalike_to_oil_rate, 4),
            "lookalike_rejection_rate": round(lookalike_rejection_rate, 4),
            "headline_summary": (
                f"Oil->Lookalike: {oil_to_lookalike_rate*100:.2f}% ({oil_to_lookalike_count} px) | "
                f"Lookalike->Oil: {lookalike_to_oil_rate*100:.2f}% ({lookalike_to_oil_count} px) | "
                f"Lookalike Rejection Rate: {lookalike_rejection_rate*100:.2f}%"
            ),
        },
        "confusion_matrix": cm.tolist(),
        "class_order": [names[i] for i in range(num_classes)],
    }
