"""预算守卫（纯函数，便于单测）。

规则（PRD FR-012 / §7.3）：
- 单任务设金额上限，超限停止新调用，保留已完成结果；
- 金额一律用「分」的整数。
"""


def check_budget(unit_price_fen: int, spent_fen: int, budget_fen: int) -> tuple[bool, str]:
    """返回 (是否放行, 拒绝原因)。"""
    if unit_price_fen <= 0:
        return False, "模型单价比未配置或无效，无法生成"
    if budget_fen <= 0:
        return False, "预算上限必须大于 0"
    if spent_fen < 0:
        spent_fen = 0
    if spent_fen + unit_price_fen > budget_fen:
        return False, (
            f"预算不足：已花费 {_fmt(spent_fen)} 元，本次需要 {_fmt(unit_price_fen)} 元，"
            f"上限 {_fmt(budget_fen)} 元"
        )
    return True, ""


def _fmt(fen: int) -> str:
    return f"{fen / 100:.2f}"


def remaining_fen(budget_fen: int, spent_fen: int) -> int:
    return max(0, budget_fen - max(0, spent_fen))
