import pyarrow.parquet as pq
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ======================
# 1. 读取 parquet
# ======================

f = 'data/demo_1000.parquet'

pf = pq.ParquetFile(f)

# 直接转 pandas
df = pf.read().to_pandas()

print(df.columns.tolist())

# ======================
# 2. 提取 87/90/91
# ======================

def filter_valid(arr_col, expected_len=10):
    valid = []

    for x in arr_col:
        if x is None:
            continue

        x = np.asarray(x)

        # if len(x) == expected_len:
        valid.append(x)

    return np.stack(valid)

feat87 = filter_valid(df['user_dense_feats_87'].values)
feat90 = filter_valid(df['user_dense_feats_90'].values)
feat91 = filter_valid(df['user_dense_feats_91'].values)

print(feat87.shape)
print(feat90.shape)
print(feat91.shape)

# ======================
# 3. 单样本趋势图
# ======================

sample_ids = [0, 1, 2, 3, 4]

for sid in sample_ids:

    plt.figure(figsize=(8,4))

    plt.plot(
        feat87[sid],
        marker='o',
        linewidth=2,
        label='fid87'
    )

    plt.plot(
        feat90[sid],
        marker='s',
        linewidth=2,
        label='fid90'
    )

    plt.plot(
        feat91[sid],
        marker='^',
        linewidth=2,
        label='fid91'
    )

    plt.xticks(range(10))
    plt.xlabel("Dimension / Bin")
    plt.ylabel("Value")
    plt.title(f"Trend Curve of Sample {sid}")

    plt.legend()
    plt.grid(True)

    plt.show()

# ======================
# 4. 平均趋势图（最重要）
# ======================

mean87 = feat87.mean(axis=0)
mean90 = feat90.mean(axis=0)
mean91 = feat91.mean(axis=0)

plt.figure(figsize=(9,5))

plt.plot(mean87, marker='o', linewidth=3, label='fid87 mean')
plt.plot(mean90, marker='s', linewidth=3, label='fid90 mean')
plt.plot(mean91, marker='^', linewidth=3, label='fid91 mean')

plt.xticks(range(10))
plt.xlabel("Dimension / Bin")
plt.ylabel("Mean Value")

plt.title("Average Trend Structure")

plt.legend()
plt.grid(True)

plt.show()

# ======================
# 5. Heatmap：维度相关性
# ======================

corr87 = pd.DataFrame(feat87).corr()
corr90 = pd.DataFrame(feat90).corr()
corr91 = pd.DataFrame(feat91).corr()

fig, axes = plt.subplots(1, 3, figsize=(18,5))

im0 = axes[0].imshow(corr87, vmin=-1, vmax=1)
axes[0].set_title("fid87 correlation")

im1 = axes[1].imshow(corr90, vmin=-1, vmax=1)
axes[1].set_title("fid90 correlation")

im2 = axes[2].imshow(corr91, vmin=-1, vmax=1)
axes[2].set_title("fid91 correlation")

for ax in axes:
    ax.set_xticks(range(10))
    ax.set_yticks(range(10))

fig.colorbar(im2, ax=axes.ravel().tolist())

plt.show()

# ======================
# 6. shuffle 对比实验
# ======================

x = feat87[0]

perm = np.random.permutation(10)

plt.figure(figsize=(8,4))

plt.plot(
    x,
    marker='o',
    linewidth=3,
    label='original'
)

plt.plot(
    x[perm],
    marker='x',
    linewidth=3,
    label='shuffled'
)

plt.xticks(range(10))
plt.xlabel("Dimension / Bin")
plt.ylabel("Value")

plt.title("Original vs Shuffled")

plt.legend()
plt.grid(True)

plt.show()

# ======================
# 7. 相邻差分（验证 trend）
# ======================

diff87 = np.diff(feat87, axis=1)
diff90 = np.diff(feat90, axis=1)
diff91 = np.diff(feat91, axis=1)

mean_diff87 = diff87.mean(axis=0)
mean_diff90 = diff90.mean(axis=0)
mean_diff91 = diff91.mean(axis=0)

plt.figure(figsize=(9,5))

plt.plot(
    mean_diff87,
    marker='o',
    linewidth=3,
    label='fid87 diff'
)

plt.plot(
    mean_diff90,
    marker='s',
    linewidth=3,
    label='fid90 diff'
)

plt.plot(
    mean_diff91,
    marker='^',
    linewidth=3,
    label='fid91 diff'
)

plt.xlabel("Difference Index")
plt.ylabel("Mean Difference")

plt.title("Local Trend Statistics")

plt.legend()
plt.grid(True)

plt.show()

# ======================
# 8. PCA 可视化
# ======================

from sklearn.decomposition import PCA

pca = PCA(n_components=2)

z87 = pca.fit_transform(feat87)

plt.figure(figsize=(6,6))

plt.scatter(
    z87[:,0],
    z87[:,1],
    s=8,
    alpha=0.5
)

plt.xlabel("PC1")
plt.ylabel("PC2")

plt.title("PCA of fid87")

plt.grid(True)

plt.show()