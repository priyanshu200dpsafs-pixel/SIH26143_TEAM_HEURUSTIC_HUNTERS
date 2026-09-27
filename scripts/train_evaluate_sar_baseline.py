"""
Training, Validation, and Comprehensive Evaluation Pipeline for SAR U-Net Baseline.

Executes:
1. Deterministic training on Krestenitis train split (672 images, with training augmentations).
2. Validation on clean Krestenitis val split (160 images, 0 augmentation, 0 leakage).
3. Saves model checkpoint to models/sar_unet_baseline_best.pt and config to models/sar_unet_config.json.
4. Comprehensive test evaluation on Krestenitis test split (208 images):
   - 4x4 Confusion Matrix
   - Per-class IoU, Precision, Recall, F1, Pixel Accuracy
   - MANDATORY:
     * Oil -> Look-alike confusion
     * Look-alike -> Oil confusion
     * Look-alike Rejection Rate
5. Dedicated Hard-Negative Evaluation on look-alike test scenes.
6. Generates visual failure analysis figures (RAW SAR, GT, PRED, ERROR MAP) for failure catalogue.
"""

import json
import os
from pathlib import Path
import random
import time
from typing import Any, Dict, List, Tuple
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from src.detection.dataset_adapters import (
    KRESTENITIS_CLASSES,
    KRESTENITIS_ID_TO_COLOR,
    KrestenitisDataset,
    encode_krestenitis_class_mask,
)
from src.detection.preprocessing import TrainingAugmentor
from src.detection.sar_segmentation import UNetBaseline
from src.detection.metrics import compute_confusion_matrix, evaluate_segmentation_metrics


def set_deterministic_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def create_error_map(pred: np.ndarray, gt: np.ndarray) -> np.ndarray:
    """
    Create an RGB error map highlighting detection discrepancies:
    - Black: Correct Background / Water (TN)
    - Green: True Positive Oil (pred==1 and gt==1)
    - Red: False Positive Oil (pred==1 and gt!=1, including look-alikes mistaken for oil)
    - Blue: False Negative Oil (pred!=1 and gt==1, missed oil)
    - Yellow: Look-alike / Water confusion (pred==2 and gt!=2 or pred!=2 and gt==2)
    """
    h, w = pred.shape
    err_rgb = np.zeros((h, w, 3), dtype=np.uint8)
    
    # Correct background/water
    err_rgb[(pred == gt) & (gt == 3)] = [20, 40, 60]
    
    # True Positive Oil: Green
    err_rgb[(pred == 1) & (gt == 1)] = [0, 255, 0]
    
    # False Positive Oil: Red
    err_rgb[(pred == 1) & (gt != 1)] = [255, 0, 0]
    
    # False Negative Oil: Blue
    err_rgb[(pred != 1) & (gt == 1)] = [0, 100, 255]
    
    # Other errors (e.g. look-alike misclassified): Yellow
    other_err = (pred != gt) & (pred != 1) & (gt != 1)
    err_rgb[other_err] = [230, 200, 40]
    
    return err_rgb


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Train or evaluate SAR baseline model.')
    parser.add_argument('--eval-only', action='store_true', help='Evaluate saved checkpoint on test set.')
    args = parser.parse_args()

    set_deterministic_seed(42)
    
    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    print(f'=== Starting Phase 3 SAR Baseline Training on {device} ===')
    
    models_dir = Path('models')
    results_dir = Path('data/results')
    failures_dir = Path('docs/failure_analysis')
    models_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    failures_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Dataset loaders
    augmentor = TrainingAugmentor(p_hflip=0.5, p_vflip=0.5, p_rot90=0.5, seed=42)
    train_dataset = KrestenitisDataset(split='train', target_size=(256, 256), transform=augmentor)
    val_dataset = KrestenitisDataset(split='val', target_size=(256, 256), transform=None)
    test_dataset = KrestenitisDataset(split='test', target_size=(256, 256), transform=None)
    
    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=16, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=16, shuffle=False, num_workers=0)
    
    print(f'Datasets loaded: Train={len(train_dataset)}, Val={len(val_dataset)}, Test={len(test_dataset)}')
    
    # 2. Model initialization
    model = UNetBaseline(n_channels=3, n_classes=4, features=(32, 64, 128, 256))
    model.to(device)
    
    # Class weighting: Background=1.0, Oil=3.5, Lookalike=2.0, Water=1.0
    class_weights = torch.tensor([1.0, 3.5, 2.0, 1.0], dtype=torch.float32, device=device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=8)
    
    epochs = 8
    best_val_oil_iou = 0.0
    best_checkpoint_path = models_dir / 'sar_unet_baseline_best.pt'
    
    train_start_time = time.time()
    
    if not args.eval_only:
        for epoch in range(1, epochs + 1):
            model.train()
            train_loss = 0.0
            for batch in train_loader:
                imgs = batch['image'].to(device)
                masks = batch['mask'].to(device)
                
                optimizer.zero_grad()
                logits = model(imgs)
                loss = criterion(logits, masks)
                loss.backward()
                optimizer.step()
                train_loss += loss.item() * imgs.size(0)
                
            scheduler.step()
            train_loss /= len(train_dataset)
            
            # Validation pass
            model.eval()
            val_cm = np.zeros((4, 4), dtype=np.int64)
            with torch.no_grad():
                for batch in val_loader:
                    imgs = batch['image'].to(device)
                    masks = batch['mask']
                    logits = model(imgs)
                    preds = torch.argmax(logits, dim=1).cpu()
                    val_cm += compute_confusion_matrix(preds, masks, num_classes=4)
                    
            val_metrics = evaluate_segmentation_metrics(val_cm, KRESTENITIS_CLASSES)
            val_oil_iou = val_metrics['per_class_iou']['Oil Spill']
            val_miou = val_metrics['mean_iou']
            
            print(f'Epoch {epoch:02d}/{epochs:02d} | Train Loss: {train_loss:.4f} | Val mIoU: {val_miou:.4f} | Val Oil IoU: {val_oil_iou:.4f}')
            
            if val_oil_iou > best_val_oil_iou or epoch == 1:
                best_val_oil_iou = val_oil_iou
                torch.save({
                    'epoch': epoch,
                    'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(),
                    'val_metrics': val_metrics,
                    'config': {
                        'architecture': 'UNetBaseline',
                        'features': [32, 64, 128, 256],
                        'num_classes': 4,
                        'input_size': [256, 256],
                        'class_weights': [1.0, 3.5, 2.0, 1.0],
                        'learning_rate': 1e-3,
                        'epochs': epochs,
                        'seed': 42,
                    }
                }, best_checkpoint_path)
                
        train_duration = time.time() - train_start_time
        print(f'Training complete in {train_duration:.1f}s. Best Val Oil IoU: {best_val_oil_iou:.4f}')
        
        # Save training configuration JSON
        config_dict = {
            'training_timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
            'random_seed': 42,
            'package_versions': {
                'torch': torch.__version__,
                'numpy': np.__version__,
                'pillow': Image.__version__,
            },
            'dataset_identifiers': {
                'name': 'Krestenitis SAR Dataset',
                'train_size': len(train_dataset),
                'val_size': len(val_dataset),
                'test_size': len(test_dataset),
                'target_size': [256, 256],
                'classes': KRESTENITIS_CLASSES,
            },
            'architecture': {
                'model_name': 'UNetBaseline',
                'channels': [32, 64, 128, 256, 512],
                'parameters_count': sum(p.numel() for p in model.parameters()),
            },
            'training_config': {
                'epochs': epochs,
                'batch_size': 16,
                'optimizer': 'AdamW',
                'initial_lr': 1e-3,
                'weight_decay': 1e-4,
                'loss_function': 'Weighted Cross-Entropy',
                'class_weights': [1.0, 3.5, 2.0, 1.0],
                'device': str(device),
                'training_duration_seconds': round(train_duration, 2),
            }
        }
        with open(models_dir / 'sar_unet_config.json', 'w') as f:
            json.dump(config_dict, f, indent=2)
        
    # 3. Comprehensive Evaluation on Test Set (208 scenes)
    print('Evaluating best model on Test Set...')
    checkpoint = torch.load(best_checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    test_cm = np.zeros((4, 4), dtype=np.int64)
    all_test_predictions = []
    
    with torch.no_grad():
        for b_idx, batch in enumerate(test_loader):
            imgs = batch['image'].to(device)
            masks = batch['mask']
            filenames = batch['filename']
            
            logits = model(imgs)
            probs = torch.softmax(logits, dim=1).cpu().numpy()
            preds = torch.argmax(logits, dim=1).cpu().numpy()
            masks_np = masks.numpy()
            imgs_np = imgs.cpu().numpy()
            
            test_cm += compute_confusion_matrix(preds, masks_np, num_classes=4)
            
            for i in range(len(filenames)):
                all_test_predictions.append({
                    'filename': filenames[i],
                    'raw_image': imgs_np[i],
                    'true_mask': masks_np[i],
                    'pred_mask': preds[i],
                    'probs': probs[i],
                })
                
    test_metrics = evaluate_segmentation_metrics(test_cm, KRESTENITIS_CLASSES)
    print('=== TEST METRICS ===')
    print('Pixel Accuracy:', test_metrics['overall_pixel_accuracy'])
    print('Mean IoU:', test_metrics['mean_iou'])
    print('Macro F1:', test_metrics['macro_f1'])
    print('Per-class IoU:', test_metrics['per_class_iou'])
    print('Per-class F1:', test_metrics['per_class_f1'])
    print('Mandatory Analysis:', test_metrics['mandatory_oil_lookalike_analysis']['headline_summary'])
    
    # Save test metrics JSON
    with open(results_dir / 'sar_test_metrics.json', 'w') as f:
        json.dump(test_metrics, f, indent=2)
        
    # 4. Dedicated Hard-Negative Evaluation
    print('Performing Dedicated Hard-Negative Look-alike Evaluation...')
    hn_cm = np.zeros((4, 4), dtype=np.int64)
    hn_scenes_count = 0
    
    for item in all_test_predictions:
        t_mask = item['true_mask']
        # Select scenes with Look-alike ground truth
        if np.sum(t_mask == 2) > 0:
            hn_scenes_count += 1
            hn_cm += compute_confusion_matrix(item['pred_mask'], t_mask, num_classes=4)
            
    hn_metrics = evaluate_segmentation_metrics(hn_cm, KRESTENITIS_CLASSES)
    
    # Specific Hard-Negative Headline Metrics
    la_total = int(np.sum(hn_cm[2, :]))
    la_mistaken_for_oil = int(hn_cm[2, 1])
    oil_fp_rate_on_la = float(la_mistaken_for_oil / la_total) if la_total > 0 else 0.0
    la_rejection_rate = 1.0 - oil_fp_rate_on_la
    
    oil_total = int(np.sum(hn_cm[1, :]))
    oil_tp = int(hn_cm[1, 1])
    oil_recall = float(oil_tp / oil_total) if oil_total > 0 else 0.0
    
    oil_pred_total = int(np.sum(hn_cm[:, 1]))
    oil_precision = float(oil_tp / oil_pred_total) if oil_pred_total > 0 else 0.0
    
    hn_results = {
        'total_hard_negative_scenes': hn_scenes_count,
        'total_lookalike_pixels_evaluated': la_total,
        'oil_false_positive_rate_on_lookalikes': round(oil_fp_rate_on_la, 4),
        'lookalike_rejection_rate': round(la_rejection_rate, 4),
        'oil_recall_on_hard_subset': round(oil_recall, 4),
        'oil_precision_on_hard_subset': round(oil_precision, 4),
        'hard_negative_confusion_matrix': hn_cm.tolist(),
        'headline_summary': (
            f"Hard-Negative Evaluation ({hn_scenes_count} scenes): "
            f"Look-alike Rejection Rate = {la_rejection_rate*100:.2f}% | "
            f"Oil False-Alarm Rate on Look-alikes = {oil_fp_rate_on_la*100:.2f}% | "
            f"Oil Recall = {oil_recall*100:.2f}% | "
            f"Oil Precision = {oil_precision*100:.2f}%"
        )
    }
    print(hn_results['headline_summary'])
    with open(results_dir / 'hard_negative_evaluation.json', 'w') as f:
        json.dump(hn_results, f, indent=2)
        
    # 5. Failure Analysis: Find top false positive cases
    print('Generating Failure Analysis Visualizations...')
    scored_cases = []
    for item in all_test_predictions:
        p = item['pred_mask']
        t = item['true_mask']
        # Count false positive oil pixels (predicted oil where true is lookalike or water or bg)
        fp_oil_pixels = int(np.sum((p == 1) & (t != 1)))
        fn_oil_pixels = int(np.sum((p != 1) & (t == 1)))
        total_error = fp_oil_pixels + fn_oil_pixels
        scored_cases.append((fp_oil_pixels, total_error, item))
        
    # Sort descending by false positive oil count
    scored_cases.sort(key=lambda x: (x[0], x[1]), reverse=True)
    
    failure_catalog = []
    # Save top 4 distinct failure examples
    for f_idx, (fp_count, total_err, item) in enumerate(scored_cases[:4]):
        fname = item['filename']
        stem = Path(fname).stem
        img_arr = item['raw_image'].transpose(1, 2, 0) # H, W, 3
        gt_rgb = encode_krestenitis_class_mask(item['true_mask'])
        pred_rgb = encode_krestenitis_class_mask(item['pred_mask'])
        err_rgb = create_error_map(item['pred_mask'], item['true_mask'])
        
        fig, axes = plt.subplots(1, 4, figsize=(16, 4))
        
        axes[0].imshow(np.clip(img_arr, 0.0, 1.0))
        axes[0].set_title(f'RAW SAR: {stem}', fontsize=10)
        axes[0].axis('off')
        
        axes[1].imshow(gt_rgb)
        axes[1].set_title('GROUND TRUTH (Pink=Oil, Yellow=Lookalike, Blue=Sea)', fontsize=9)
        axes[1].axis('off')
        
        axes[2].imshow(pred_rgb)
        axes[2].set_title('U-NET PREDICTION (Pink=Oil, Yellow=Lookalike)', fontsize=9)
        axes[2].axis('off')
        
        axes[3].imshow(err_rgb)
        axes[3].set_title(f'ERROR MAP (Red=FP [{fp_count}px], Blue=FN, Green=TP)', fontsize=9)
        axes[3].axis('off')
        
        plt.tight_layout()
        out_fig_path = failures_dir / f'failure_case_{f_idx+1}_{stem}.png'
        plt.savefig(out_fig_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        # Categorize failure mode
        gt_mask = item['true_mask']
        pred_mask = item['pred_mask']
        la_in_gt = int(np.sum(gt_mask == 2))
        water_in_gt = int(np.sum(gt_mask == 3))
        oil_in_gt = int(np.sum(gt_mask == 1))
        
        if la_in_gt > 0 and np.sum((pred_mask == 1) & (gt_mask == 2)) > 50:
            mode = 'Look-alike Misclassification'
            explanation = 'Low backscatter natural slick / biogenic film was misclassified as mineral hydrocarbon.'
        elif oil_in_gt > 0 and fn_oil_pixels > 100:
            mode = 'Fragmented / Low Contrast Slick Under-detection'
            explanation = 'Weak radar backscatter contrast and narrow feathering caused false negative segmentation.'
        elif water_in_gt > 0 and np.sum((pred_mask == 1) & (gt_mask == 3)) > 50:
            mode = 'Calm Water / Specular Sea False Alarm'
            explanation = 'Very low wind calm water patch produced mirror-like specular reflection resembling oil slick.'
        else:
            mode = 'Boundary Feathering / Edge Uncertainty'
            explanation = 'Uncertainty along slick perimeter and transition zone between oil and sea surface.'
            
        failure_catalog.append({
            'case_id': f'CASE_{f_idx+1}',
            'filename': fname,
            'image_artifact': str(out_fig_path),
            'failure_mode': mode,
            'fp_oil_pixels': fp_count,
            'fn_oil_pixels': fn_oil_pixels,
            'analysis': explanation,
        })
        
    with open(results_dir / 'failure_catalogue.json', 'w') as f:
        json.dump(failure_catalog, f, indent=2)
        
    print(f'Saved {len(failure_catalog)} failure analysis figures to {failures_dir}')
    print('=== All Training, Evaluation, and Analysis Tasks Complete ===')

if __name__ == '__main__':
    main()
