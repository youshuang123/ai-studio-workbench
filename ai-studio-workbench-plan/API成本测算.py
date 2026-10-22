#!/usr/bin/env python3
"""API-only 成本测算（RMB，低成本优先）。

目标：
  单张图 <= 0.10 元
  单分钟视频 <= 1.00 元

用法：
    python3 API成本测算.py

所有参数都在文件顶部，按你的真实报价修改。
"""

# ===================== 可调参数 =====================
RETRY_RATE = 0.15          # 失败/重试率
CACHE_HIT = 0.20           # 缓存命中率（命中不调用 API）
IMAGE_QA = 0.005           # 每张 QA 成本（元）
IMAGE_STORAGE = 0.002      # 每张存储/带宽（元）
VIDEO_AUDIO_PER_MIN = 0.05 # 每分钟音频/TTS（元）
VIDEO_QA_PER_MIN = 0.02    # 每分钟视频 QA（元）
VIDEO_STORAGE_PER_MIN = 0.02
MOTION_RENDER_PER_MIN = 0.02  # FFmpeg/轻动效渲染（元/分钟）
KEYFRAMES_PER_MIN = 10     # 轻动效方案每分钟关键帧数

TARGET_IMAGE = 0.10
TARGET_VIDEO = 1.00

# 图片 API 单价（元/张）
IMAGE_API_PRICES = [0.03, 0.05, 0.06, 0.08, 0.10, 0.15, 0.30, 0.50]
# 视频 API 单价（元/5 秒镜头）
VIDEO_API_PRICES_5S = [0.03, 0.05, 0.08, 0.10, 0.20, 0.30, 0.50, 1.00]
SECONDS_PER_CLIP = 5
CLIPS_PER_MIN = 60 / SECONDS_PER_CLIP


def image_cost(api_price: float) -> float:
    return api_price * (1 + RETRY_RATE) * (1 - CACHE_HIT) + IMAGE_QA + IMAGE_STORAGE


def motion_video_cost() -> float:
    keyframe_cost = KEYFRAMES_PER_MIN * image_cost(0.06)
    return keyframe_cost + MOTION_RENDER_PER_MIN + VIDEO_AUDIO_PER_MIN + VIDEO_QA_PER_MIN + VIDEO_STORAGE_PER_MIN


def i2v_video_cost(api_price_5s: float) -> float:
    generation = api_price_5s * CLIPS_PER_MIN * (1 + RETRY_RATE)
    return generation + VIDEO_AUDIO_PER_MIN + VIDEO_QA_PER_MIN + VIDEO_STORAGE_PER_MIN


def fmt_ok(value: float, target: float) -> str:
    return "✅" if value <= target else "❌"


def main() -> None:
    print("API-only 成本测算（RMB，示例参数）")
    print(f"重试率 {RETRY_RATE:.0%}，缓存命中 {CACHE_HIT:.0%}")
    print(f"目标：图片 ≤ ¥{TARGET_IMAGE:.2f}/张，视频 ≤ ¥{TARGET_VIDEO:.2f}/分钟\n")

    print("== 图片 ==")
    print(f"{'API 单价/张':>12}{'有效成本/张':>14}{'达标':>6}  说明")
    print("-" * 56)
    for price in IMAGE_API_PRICES:
        cost = image_cost(price)
        print(f"¥{price:>10.2f}{cost:>14.4f}{fmt_ok(cost, TARGET_IMAGE):>6}  " +
              ("可做默认档" if cost <= TARGET_IMAGE else "只能做精品/升级档"))
    print("\n== 视频：关键帧 + 轻动效 ==")
    motion = motion_video_cost()
    print(f"成本 ≈ ¥{motion:.2f}/分钟 {fmt_ok(motion, TARGET_VIDEO)}  "
          f"(每分钟 {KEYFRAMES_PER_MIN} 张关键帧)")
    print("\n== 视频：完整 I2V API ==")
    print(f"{'API 单价/5秒':>14}{'成本/分钟':>12}{'达标':>6}  说明")
    print("-" * 62)
    for price in VIDEO_API_PRICES_5S:
        cost = i2v_video_cost(price)
        print(f"¥{price:>12.2f}{cost:>12.2f}{fmt_ok(cost, TARGET_VIDEO):>6}  " +
              ("勉强可做低质档" if cost <= TARGET_VIDEO else "需要提价/降质/自托管"))
    print("\n== 结论模板 ==")
    print("- 图片：API 单价 ≤¥0.08/张、重试 ≤15%、缓存 ≥20% 时，¥0.10/张可行。")
    print("- 视频：完整 I2V 想压到 ¥1/分钟，API 需低到 ¥0.05/5秒 左右，正常质量不现实。")
    print("- MVP 建议：关键帧 + 轻动效；完整 I2V 放 P1 或精品付费档。")
    print("- 如果 ¥1/分钟是对外售价而不是成本，请把售价和成本分开算。")


if __name__ == "__main__":
    main()
