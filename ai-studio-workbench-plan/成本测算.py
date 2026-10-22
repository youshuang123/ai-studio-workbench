#!/usr/bin/env python3
"""模型自托管 vs API 成本测算（示例版，参数都在文件顶部，直接改）。

用法：
    python3 成本测算.py

注意：GPU 价格、吞吐、重试率、运维分摊都因环境而异，这里的默认值只是示例。
"""

from dataclasses import dataclass

# ===================== 可调参数 =====================
GPU_HOURLY = {
    "H100": 2.50,
    "H200": 3.50,
    "L40S": 1.20,
    "A100-80G": 1.80,
}
OPS_OVERHEAD = 0.30          # 运维/平台分摊：30%
MONTHLY_FIXED = 300.0        # 每模型每月固定工程/监控成本（示例，美元）
STORAGE_PER_ASSET = 0.0002   # 每资产存储/带宽成本（示例，美元）

# 图片：每 GPU 每小时吞吐（张）
IMAGE_CASES = [
    # name, gpu, throughput_per_hour, api_price_per_image
    ("FLUX.1 [schnell] 草稿", "L40S", 600, 0.02),
    ("FLUX.1 [dev] 标准", "H100", 300, 0.04),
    ("Qwen-Image 标准", "H100", 250, 0.04),
]

# 视频：每条 5 秒视频占用 GPU 分钟数
VIDEO_CASES = [
    # name, gpu, gpu_minutes_per_clip, api_price_per_clip
    ("Wan2.2-I2V 5s 标准", "H100", 5.0, 0.80),
    ("HunyuanVideo 5s", "H100", 8.0, 0.80),
]

# LLM：每小时可处理请求数
LLM_CASES = [
    # name, gpu, requests_per_hour, api_price_per_request
    ("Qwen3-32B 路由", "L40S", 2000, 0.001),
    ("Qwen3-235B 复杂拆解", "H100", 500, 0.004),
]


# ===================== 计算 =====================
@dataclass
class Result:
    name: str
    self_host_unit: float
    api_unit: float
    break_even: float


def break_even(api_unit: float, self_unit: float, monthly_fixed: float) -> float:
    diff = api_unit - self_unit
    if diff <= 0:
        return 0.0
    return monthly_fixed / diff


def image_result(name: str, gpu: str, throughput: float, api_price: float) -> Result:
    gpu_cost = GPU_HOURLY[gpu] / throughput
    self_unit = gpu_cost * (1 + OPS_OVERHEAD) + STORAGE_PER_ASSET
    api_unit = api_price * 1.10  # 假设 10% 重试/失败损耗
    return Result(name, self_unit, api_unit, break_even(api_unit, self_unit, MONTHLY_FIXED))


def video_result(name: str, gpu: str, minutes: float, api_price: float) -> Result:
    gpu_cost = GPU_HOURLY[gpu] * (minutes / 60.0)
    self_unit = gpu_cost * (1 + OPS_OVERHEAD) + STORAGE_PER_ASSET * 5
    api_unit = api_price * 1.15
    return Result(name, self_unit, api_unit, break_even(api_unit, self_unit, MONTHLY_FIXED))


def llm_result(name: str, gpu: str, rph: float, api_price: float) -> Result:
    gpu_cost = GPU_HOURLY[gpu] / rph
    self_unit = gpu_cost * (1 + OPS_OVERHEAD)
    api_unit = api_price * 1.10
    return Result(name, self_unit, api_unit, break_even(api_unit, self_unit, MONTHLY_FIXED))


def print_table(title: str, results: list[Result], unit: str) -> None:
    print(f"\n== {title} ==")
    print(f"{'方案':<28}{'自托管/单位':>14}{'API/单位':>12}{'盈亏平衡量':>14}  建议")
    print("-" * 82)
    for r in results:
        if r.self_host_unit < r.api_unit:
            advice = f"月量 > {r.break_even:,.0f} 时自托管更省" if r.break_even else "自托管更省"
        else:
            advice = "API 更省/更省心"
        print(f"{r.name:<28}{r.self_host_unit:>13.4f}{r.api_unit:>12.4f}{r.break_even:>14,.0f}  {advice}")
    print(f"单位：{unit}；盈亏平衡量 = 月固定成本 / (API 单价 - 自托管单价)")


def main() -> None:
    print("模型成本测算（示例参数，请按真实报价修改文件顶部）")
    print(f"GPU 价格：{GPU_HOURLY}")
    print(f"运维分摊：{OPS_OVERHEAD:.0%}；每模型月固定成本：${MONTHLY_FIXED:,.0f}")

    print_table("图片", [image_result(*c) for c in IMAGE_CASES], "美元/张")
    print_table("视频", [video_result(*c) for c in VIDEO_CASES], "美元/条")
    print_table("LLM", [llm_result(*c) for c in LLM_CASES], "美元/次")

    print("\n结论模板：")
    print("- 低月量：API 优先，省运维、省冷启动。")
    print("- 高月量：自托管标准模型，API 只留给精品/长尾。")
    print("- 视频：批量镜头自托管 Wan2.2，关键镜头用 Kling/Veo。")
    print("- 任何结论都要用真实吞吐、重试率、GPU 利用率复算。")


if __name__ == "__main__":
    main()
