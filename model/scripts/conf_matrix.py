import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix
import pandas as pd

# --- Configuration for Plotting ---
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Inter', 'Arial'] # Using a standard readable font

def plot_confusion_matrix_from_counts(tn, fp, fn, tp, labels=['Normal', 'Anomaly'], title='Confusion Matrix (Ensemble)'):
    cm_array = np.array([[tn, fp], [fn, tp]])
    cm_df = pd.DataFrame(cm_array, index=labels, columns=labels)

    # --- Force square cells ---
    plt.figure(figsize=(5, 5))  # Adjust size as needed
    ax = sns.heatmap(
        cm_df,
        annot=True,
        fmt='d',
        cmap='Greens',
        cbar=True,
        linewidths=1.2,
        linecolor='white',
        cbar_kws={'label': 'Sample Count'},
        square=True,
        annot_kws={"size": 24}    # Annotation font size
    )

    plt.title(title, fontsize=16, pad=20)
    plt.ylabel('True Label', fontsize=14)
    plt.xlabel('Predicted Label', fontsize=14)
    
    # Fix for matplotlib/seaborn cutting off the top/bottom cells
    plt.ylim(len(cm_df), 0)
    plt.show()
# --- Custom Input Section ---
print("--- Confusion Matrix Generator (Scikit-learn Style) ---")

# Use the example values from the HTML file for demonstration
try:
    TN_INPUT = int(input("Enter True Negative (TN) count (e.g., 1300): ") or 1300)
    FP_INPUT = int(input("Enter False Positive (FP) count (e.g., 0): ") or 0)
    FN_INPUT = int(input("Enter False Negative (FN) count (e.g., 346): ") or 346)
    TP_INPUT = int(input("Enter True Positive (TP) count (e.g., 2085): ") or 2085)
except ValueError:
    print("\nError: Please enter valid integers. Using default values.")
    TN_INPUT, FP_INPUT, FN_INPUT, TP_INPUT = 1283, 17, 151, 2280


# --- Execution ---
# Class labels used in the HTML version
CLASS_LABELS = ['Normal', 'Anomaly']

print(f"\nGenerating matrix with: TN={TN_INPUT}, FP={FP_INPUT}, FN={FN_INPUT}, TP={TP_INPUT}")

# Plot the matrix
plot_confusion_matrix_from_counts(TN_INPUT, FP_INPUT, FN_INPUT, TP_INPUT, labels=CLASS_LABELS)

# --- BONUS: Example using Scikit-learn's built-in function to verify ---
# If you have actual true and predicted labels (e.g., y_true and y_pred),
# you would normally use the built-in function like this:

# Step 1: Create fake true and predicted labels that result in the desired counts
# y_true = [0]*1300 + [0]*0 + [1]*346 + [1]*2085 
# y_pred = [0]*1300 + [1]*0 + [0]*346 + [1]*2085

# Step 2: Calculate the confusion matrix from labels
# cm = confusion_matrix(y_true, y_pred)
# print("\nVerification Matrix from sklearn.metrics.confusion_matrix:\n", cm)

# Step 3: Plot the matrix (This requires y_true and y_pred)
# You would use a slightly modified plotting function for this.
