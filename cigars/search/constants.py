"""搜索专用常量"""

# 过期时间选项（模板/前端使用）
DURATION_CHOICES = [
    (1, '1 小时'),
    (6, '6 小时'),
    (24, '24 小时'),
    (72, '3 天'),
    (168, '7 天'),
    (720, '30 天'),
]

# 特别款类型权重（降权）
RELEASE_TYPE_PENALTY = {
    'Limited Edition Series': 10,
    'Replica Antique Humidor Series': 10,
    'Commemorative Release': 10,
    'Grand Reserve Series': 10,
    'Reserve Series': 10,
    'Aged Habanos Series': 10,
    'Vintage Series': 10,
    'Chinese Year Series': 10,
    'Millennium Reserve Series': 10,
    'Special Production': 10,
}

# 默认特别款降权（未在上方明确列出的）
DEFAULT_RELEASE_TYPE_PENALTY = 3

# 常规款加分
REGULAR_RELEASE_BONUS = 5

# 多词查询加分
MULTI_TERM_HIT_BRAND_BONUS = 20
MULTI_TERM_HIT_OTHER_BONUS = 10
MULTI_TERM_ALL_HIT_BONUS = 25

# 单查询词额外加分
SINGLE_TERM_HIT_BONUS = 15

# 产品名优先于仅在品型/常见名中命中的候选
PRODUCT_NAME_EXACT_BONUS = 30
PRODUCT_NAME_HIT_BONUS = 15

# 基础分 ratio 系数
BASE_RATIO_FACTOR = 0.85

# 默认返回结果数
DEFAULT_RESULT_LIMIT = 30

# 最低相关性分数，避免无关查询也返回最高分结果
MIN_SEARCH_SCORE = 45
