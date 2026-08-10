"""工具接入：纯本地实现的工具函数，供 LLM 通过 tool_calls 调用

工具列表：
- estimate_calories(ingredients)   按食材估算整道菜热量
- seasonal_ingredients(month)      当月时令食材
- convert_units(qty, from, to)     单位换算
- nutrition_advice(goal, meal)     营养建议（规则化）
"""
import json
from datetime import datetime

# 常见食材每 100g 热量（kcal），粗略值，用于估算
CALORIE_TABLE = {
    "米饭": 116, "大米": 346, "面粉": 366, "面条": 110, "馒头": 223,
    "猪肉": 395, "猪五花": 508, "猪里脊": 155, "牛肉": 125, "羊肉": 203,
    "鸡胸肉": 133, "鸡腿": 181, "鸡蛋": 144, "鸭蛋": 180, "鱼肉": 113,
    "虾": 93, "豆腐": 84, "豆浆": 31, "牛奶": 54, "酸奶": 72,
    "土豆": 77, "红薯": 86, "玉米": 112, "山药": 57, "南瓜": 23,
    "西红柿": 20, "黄瓜": 16, "茄子": 23, "青椒": 22, "白菜": 20,
    "菠菜": 28, "芹菜": 20, "西兰花": 36, "胡萝卜": 39, "白萝卜": 21,
    "洋葱": 40, "大蒜": 128, "生姜": 41, "香菇": 26, "木耳": 27,
    "冬瓜": 12, "豆角": 34, "莲藕": 73, "花生": 574, "核桃": 646,
    "食用油": 899, "猪油": 897, "糖": 400, "盐": 0, "酱油": 63,
    "醋": 31, "料酒": 66, "蚝油": 114, "淀粉": 346, "豆瓣酱": 178,
    "辣椒": 40, "花椒": 258, "葱": 32, "香菜": 33,
}

# 时令食材（中国中部地区大致月份，简单版）
SEASONAL = {
    1: ["白菜", "萝卜", "菠菜", "冬笋", "羊肉", "牛肉"],
    2: ["春笋", "菠菜", "韭菜", "芹菜", "萝卜", "鲈鱼"],
    3: ["春笋", "韭菜", "荠菜", "香椿", "豌豆", "鳜鱼"],
    4: ["春笋", "蚕豆", "豌豆", "芦笋", "草莓", "河虾"],
    5: ["蒜薹", "蚕豆", "苋菜", "黄瓜", "樱桃", "小龙虾"],
    6: ["黄瓜", "西红柿", "茄子", "豆角", "西瓜", "黄鳝"],
    7: ["苦瓜", "丝瓜", "冬瓜", "毛豆", "莲蓬", "鸭子"],
    8: ["莲藕", "菱角", "茄子", "丝瓜", "葡萄", "梭子蟹"],
    9: ["莲藕", "芋头", "南瓜", "板栗", "大闸蟹", "石榴"],
    10: ["莲藕", "山药", "柿子", "柚子", "大闸蟹", "鲈鱼"],
    11: ["萝卜", "白菜", "山药", "冬枣", "羊肉", "带鱼"],
    12: ["白菜", "萝卜", "冬笋", "菠菜", "羊肉", "鳗鱼"],
}

# 营养建议规则库
NUTRITION_TIPS = {
    "低卡": "优先蒸煮炖拌，少油少糖；肉类选鸡胸、鱼虾、瘦牛肉；主食掺杂粮或减半；每餐蔬菜占一半。",
    "高蛋白": "每餐保证一掌大小的肉/蛋/豆制品；鸡蛋、鸡胸、鱼虾、豆腐轮换；运动后 1 小时内补蛋白效果最好。",
    "控糖": "主食换成糙米/燕麦/杂粮，先吃菜再吃肉最后吃主食；避开勾芡、糖醋、红烧这类重糖做法。",
    "减盐": "用醋、柠檬、香料代替部分盐；酱油蚝油都是盐大户，放了一样少放另一样；出锅前再放盐。",
    "补钙": "每天一杯奶或酸奶；豆腐、虾皮、芝麻酱都是高钙食材；少喝浓茶咖啡影响钙吸收。",
    "护胃": "少辛辣油腻，多粥汤软食；细嚼慢咽；避免冰饮配热食。",
}


def estimate_calories(ingredients: list[str]) -> dict:
    """按食材粗略估算整道菜热量。ingredients: ["鸡蛋2个", "西红柿3个"]"""
    result = {}
    total = 0
    for item in ingredients:
        item = str(item).strip()
        # 提取食材名（去掉数量词和单位）
        name = item
        for ch in "0123456789.个只颗斤克毫升勺碗块片根把":
            name = name.replace(ch, "")
        kcal_per_100 = CALORIE_TABLE.get(name)
        if kcal_per_100 is None:
            # 尝试模糊匹配：取名称前2字
            kcal_per_100 = CALORIE_TABLE.get(name[:2])
        if kcal_per_100 is None:
            result[item] = "未知（不在内置表里）"
            continue
        # 从数量词估克数（极简规则）
        grams = 100
        if "个" in item or "只" in item:
            try:
                grams = int(item.split("个")[0].split("只")[0]) * 80
            except ValueError:
                grams = 160
        elif "斤" in item:
            grams = 500
        elif "克" in item:
            try:
                grams = int(item.replace("克", "").strip())
            except ValueError:
                grams = 100
        kcal = round(kcal_per_100 * grams / 100)
        result[item] = f"约{kcal}千卡"
        total += kcal
    return {"total_kcal_approx": total, "detail": result}


def seasonal_ingredients(month: int | None = None) -> dict:
    """当月时令食材。month 缺省取当前月份。"""
    if month is None:
        month = datetime.now().month
    month = int(month)
    if month < 1 or month > 12:
        return {"error": "月份需在 1-12 之间"}
    return {"month": month, "ingredients": SEASONAL.get(month, [])}


def convert_units(qty: float, from_unit: str, to_unit: str) -> dict:
    """单位换算。支持：克/千克/斤/两/毫升/升/勺/碗/杯"""
    to_gram = {"克": 1, "千克": 1000, "斤": 500, "两": 50, "公斤": 1000}
    to_ml = {"毫升": 1, "升": 1000, "勺": 15, "汤匙": 15, "茶匙": 5, "碗": 250, "杯": 240}
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        return {"error": f"数量必须是数字，收到: {qty}"}
    from_unit = str(from_unit).strip()
    to_unit = str(to_unit).strip()

    if from_unit in to_gram and to_unit in to_gram:
        return {"qty": round(qty * to_gram[from_unit] / to_gram[to_unit], 2), "unit": to_unit}
    if from_unit in to_ml and to_unit in to_ml:
        return {"qty": round(qty * to_ml[from_unit] / to_ml[to_unit], 2), "unit": to_unit}
    return {"error": f"不支持 {from_unit} → {to_unit} 的换算"}


def nutrition_advice(health_goal: str, meal_desc: str = "") -> dict:
    """营养建议。health_goal: 低卡/高蛋白/控糖/减盐/补钙/护胃"""
    goal = str(health_goal).strip()
    tip = NUTRITION_TIPS.get(goal)
    if tip is None:
        return {"error": f"暂不支持该目标：{goal}。可用：{'/'.join(NUTRITION_TIPS)}"}
    return {"health_goal": goal, "advice": tip, "meal_desc": meal_desc}


# 工具注册表：name -> (函数, 参数说明)
TOOL_REGISTRY = {
    "estimate_calories": (estimate_calories, {"ingredients": "list[str]", "desc": "食材列表，如 [\"鸡蛋2个\", \"西红柿3个\"]"}),
    "seasonal_ingredients": (seasonal_ingredients, {"month": "int（1-12，可省略）", "desc": "查询当月时令食材"}),
    "convert_units": (convert_units, {"qty": "float", "from_unit": "str", "to_unit": "str", "desc": "单位换算：克/千克/斤/两/毫升/升/勺/碗/杯"}),
    "nutrition_advice": (nutrition_advice, {"health_goal": "str（低卡/高蛋白/控糖/减盐/补钙/护胃）", "meal_desc": "str（可选）", "desc": "获取营养建议"}),
}


def run_tool(name: str, arguments: dict) -> dict:
    """执行工具，返回结果 dict。工具不存在或出错时返回错误信息。"""
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return {"error": f"未知工具: {name}"}
    func, _ = entry
    try:
        result = func(**arguments) if isinstance(arguments, dict) else func(arguments)
        return result if isinstance(result, dict) else {"result": result}
    except TypeError as e:
        return {"error": f"工具参数错误: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"工具执行失败: {e}"}


if __name__ == "__main__":
    # 自测
    print(json.dumps(estimate_calories(["鸡蛋2个", "西红柿3个", "食用油1勺"]), ensure_ascii=False))
    print(json.dumps(seasonal_ingredients(6), ensure_ascii=False))
    print(json.dumps(convert_units(1, "斤", "克"), ensure_ascii=False))
    print(json.dumps(nutrition_advice("控糖"), ensure_ascii=False))
